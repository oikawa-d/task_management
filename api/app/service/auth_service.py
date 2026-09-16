"""基本認証（登録・ログイン・ログアウト・更新・公開設定）のサービス。"""

from __future__ import annotations

from fastapi import BackgroundTasks, Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthStrategy, LoginResult
from app.core.client_ip import ClientIpInfo, resolve_client_ip
from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import (
	DuplicateEmailError,
	DuplicateUsernameError,
	EmailNotVerifiedError,
	InvalidCredentialsError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	UserInactiveError,
	is_service_unavailable_database_error,
	raise_database_error,
)
from app.core.security import get_dummy_password_hash, hash_password, verify_password
from app.models.user import User
from app.repository import login_history_repository, redis_store, user_repository
from app.schemas.auth import AuthConfigResponse, RegisterRequest
from app.service import email_verification_service
from app.service.auth_logging import (
	SERVICE_UNAVAILABLE_FAILURE_REASON,
	log_auth_state_revoke_failed,
	log_login_attempt,
	log_login_history_write_failed,
	log_user_registered,
)

_SQLSTATE_DUPLICATE_USERNAME = "P0001"
_SQLSTATE_DUPLICATE_EMAIL = "P0002"
_LOGIN_FAILURE_INVALID_CREDENTIALS = "invalid_credentials"
_LOGIN_FAILURE_USER_INACTIVE = "user_inactive"
_LOGIN_FAILURE_EMAIL_NOT_VERIFIED = "email_not_verified"
_LOGIN_FAILURE_TOO_MANY_ATTEMPTS = "too_many_attempts"


def get_auth_config(settings: BackendSettings | None = None) -> AuthConfigResponse:
	config = settings or get_backend_settings()
	return AuthConfigResponse(
		auth_mode=config.auth_mode,
		google_login_enabled=bool(
			config.google_login_enabled and config.google_client_id and config.google_client_secret
		),
		csrf_cookie_name=config.cookie_name_csrf,
	)


async def ensure_login_not_rate_limited(identifier: str, client_ip: str, settings: BackendSettings) -> None:
	failure_count = await redis_store.get_login_failure_count(identifier, client_ip)
	if failure_count >= settings.login_max_attempts:
		ttl = await redis_store.get_login_failure_ttl(identifier, client_ip)
		raise TooManyAttemptsError(retry_after=ttl if ttl > 0 else settings.login_lock_window_seconds)


async def record_login_failure(identifier: str, client_ip: str, settings: BackendSettings) -> int:
	return await redis_store.incr_login_failure(identifier, client_ip, settings.login_lock_window_seconds)


async def record_login_success(identifier: str, client_ip: str) -> None:
	await redis_store.reset_login_failure(identifier, client_ip)


def _duplicate_error_for(exc: DBAPIError) -> DuplicateUsernameError | DuplicateEmailError | None:
	sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
	if sqlstate == _SQLSTATE_DUPLICATE_USERNAME:
		return DuplicateUsernameError()
	if sqlstate == _SQLSTATE_DUPLICATE_EMAIL:
		return DuplicateEmailError()
	return None


async def register(payload: RegisterRequest, background: BackgroundTasks, request: Request, db: AsyncSession) -> User:
	if await user_repository.get_by_login_identifier(db, payload.username) is not None:
		raise DuplicateUsernameError()
	if await user_repository.get_by_email(db, payload.email) is not None:
		raise DuplicateEmailError()
	password_hash = hash_password(payload.password)
	try:
		user_id = await user_repository.create(db, payload.username, payload.email, password_hash)
		await user_repository.update_profile(
			db,
			user_id,
			payload.last_name,
			payload.first_name,
			payload.last_name_kana,
			payload.first_name_kana,
			payload.birth_date,
		)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		duplicate = _duplicate_error_for(exc)
		if duplicate is None:
			raise_database_error(exc)
		raise duplicate from exc
	user = await user_repository.get_by_id(db, user_id)
	if user is None:
		raise ServiceUnavailableError()
	await email_verification_service.issue_email_verify_token(user, background)
	log_user_registered(request, user)
	return user


async def _record_login_attempt(
	db: AsyncSession,
	user: User | None,
	identifier: str,
	request: Request,
	login_method: str,
	client_ip: str,
	*,
	success: bool,
	failure_reason: str | None,
) -> None:
	try:
		await login_history_repository.create(
			db,
			user_id=user.id if user is not None else None,
			login_identifier=identifier,
			login_method=login_method,
			ip_address=client_ip,
			user_agent=request.headers.get("user-agent"),
			success=success,
			failure_reason=failure_reason,
		)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def login(
	identifier: str,
	password: str,
	request: Request,
	response: Response,
	db: AsyncSession,
	strategy: AuthStrategy,
) -> LoginResult:
	settings = get_backend_settings()
	client_info = resolve_client_ip(request, settings.trusted_proxy_cidrs)
	client_ip = client_info.client_ip
	try:
		await ensure_login_not_rate_limited(identifier, client_ip, settings)
	except TooManyAttemptsError:
		log_login_attempt(
			request, None, client_info, identifier, strategy.mode, False, _LOGIN_FAILURE_TOO_MANY_ATTEMPTS
		)
		raise
	except Exception as exc:
		log_login_attempt(
			request, None, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise ServiceUnavailableError() from exc
	try:
		user = await user_repository.get_by_login_identifier(db, identifier)
	except ServiceUnavailableError:
		log_login_attempt(
			request, None, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise
	except Exception as exc:
		if not is_service_unavailable_database_error(exc):
			raise
		log_login_attempt(
			request, None, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise ServiceUnavailableError() from exc
	stored_hash = user.password_hash if user is not None and user.password_hash is not None else None
	password_matched = verify_password(password, stored_hash or get_dummy_password_hash())
	if user is None or stored_hash is None or not password_matched:
		login_user_id = str(user.id) if user is not None else None
		try:
			await record_login_failure(identifier, client_ip, settings)
		except Exception as exc:
			log_login_attempt(
				request, user, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
			)
			raise ServiceUnavailableError() from exc
		try:
			await _record_login_attempt(
				db,
				user,
				identifier,
				request,
				strategy.mode,
				client_ip,
				success=False,
				failure_reason=_LOGIN_FAILURE_INVALID_CREDENTIALS,
			)
		except Exception as exc:
			log_login_history_write_failed(
				request,
				user,
				client_info,
				user_id=login_user_id,
				operation="login",
				login_method=strategy.mode,
			)
			raise ServiceUnavailableError() from exc
		log_login_attempt(
			request, user, client_info, identifier, strategy.mode, False, _LOGIN_FAILURE_INVALID_CREDENTIALS
		)
		raise InvalidCredentialsError()
	try:
		await record_login_success(identifier, client_ip)
	except Exception as exc:
		log_login_attempt(
			request, user, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise ServiceUnavailableError() from exc
	if not user.is_active:
		await _record_login_failure_or_unavailable(
			db, user, identifier, request, client_info, strategy.mode, client_ip, _LOGIN_FAILURE_USER_INACTIVE
		)
		log_login_attempt(request, user, client_info, identifier, strategy.mode, False, _LOGIN_FAILURE_USER_INACTIVE)
		raise UserInactiveError()
	if user.email_verified_at is None:
		await _record_login_failure_or_unavailable(
			db, user, identifier, request, client_info, strategy.mode, client_ip, _LOGIN_FAILURE_EMAIL_NOT_VERIFIED
		)
		log_login_attempt(
			request, user, client_info, identifier, strategy.mode, False, _LOGIN_FAILURE_EMAIL_NOT_VERIFIED
		)
		raise EmailNotVerifiedError()
	try:
		login_result = await strategy.login(user, request, response)
	except Exception as exc:
		log_login_attempt(
			request, user, client_info, identifier, strategy.mode, False, SERVICE_UNAVAILABLE_FAILURE_REASON
		)
		raise ServiceUnavailableError() from exc
	login_user_id = str(user.id)
	try:
		await _record_login_attempt(
			db, user, identifier, request, strategy.mode, client_ip, success=True, failure_reason=None
		)
	except Exception as exc:
		log_login_history_write_failed(
			request,
			user,
			client_info,
			user_id=login_user_id,
			operation="login",
			login_method=strategy.mode,
		)
		try:
			await strategy.rollback_login(user, login_result, response)
		except Exception as rollback_exc:
			log_auth_state_revoke_failed(request, user, "login_rollback", client_info, user_id=login_user_id)
			raise ServiceUnavailableError() from rollback_exc
		raise ServiceUnavailableError() from exc
	log_login_attempt(request, user, client_info, identifier, strategy.mode, True, None)
	return login_result


async def _record_login_failure_or_unavailable(
	db: AsyncSession,
	user: User,
	identifier: str,
	request: Request,
	client_info: ClientIpInfo,
	login_method: str,
	client_ip: str,
	reason: str,
) -> None:
	login_user_id = str(user.id)
	try:
		await _record_login_attempt(
			db, user, identifier, request, login_method, client_ip, success=False, failure_reason=reason
		)
	except Exception as exc:
		log_login_history_write_failed(
			request,
			user,
			client_info,
			user_id=login_user_id,
			operation="login",
			login_method=login_method,
			failure_reason=SERVICE_UNAVAILABLE_FAILURE_REASON,
		)
		raise ServiceUnavailableError() from exc


async def logout(request: Request, response: Response, strategy: AuthStrategy) -> None:
	await strategy.logout(request, response)


async def refresh(request: Request, response: Response, strategy: AuthStrategy) -> LoginResult:
	return await strategy.refresh(request, response)

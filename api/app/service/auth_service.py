"""会員登録・ログイン・ログアウトと、メール認証・パスワードリセットのトークン発行・消費オーケストレーション。

参照設計書:
- docs/detailed_design/api/auth/01_post_auth_register.md〜05_get_auth_config.md
- docs/detailed_design/auth/06_token_mail.md
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthStrategy, LoginResult
from app.auth.factory import get_auth_strategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.auth.oauth import GoogleOAuthProvider, GoogleUserInfo
from app.auth.session_auth import SessionAuthStrategy
from app.core.client_ip import ClientIpInfo, resolve_client_ip
from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import (
	DuplicateEmailError,
	DuplicateUsernameError,
	EmailNotVerifiedError,
	InvalidCredentialsError,
	InvalidResetTokenError,
	InvalidStateError,
	InvalidVerifyTokenError,
	NotSupportedInModeError,
	OAuthEmailUnverifiedError,
	OAuthFailedError,
	OAuthHandoffInvalidError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	UserInactiveError,
)
from app.core.security import get_dummy_password_hash, hash_password, verify_password
from app.models.user import User
from app.repository import login_history_repository, oauth_account_repository, redis_store, user_repository
from app.schemas.auth import RegisterRequest
from app.schemas.oauth import OAuthCallbackResult, OAuthExchangeResponse, OAuthStartResult
from app.service import mail_service

# トークン長は設計上固定値だが、桁数変更の余地を残すため1箇所にまとめる（06_token_mail.md §3）。
_TOKEN_URLSAFE_BYTES = 32
logger = logging.getLogger("app.oauth")
_OAUTH_RATE_LIMIT_SCOPE = {
	"start": "oauth_start",
	"callback": "oauth_callback",
	"exchange": "oauth_exchange",
}


async def ensure_login_not_rate_limited(identifier: str, client_ip: str, settings: BackendSettings) -> None:
	"""現在の失敗回数が上限に達している場合は`TooManyAttemptsError`を送出する。"""
	failure_count = await redis_store.get_login_failure_count(identifier, client_ip)
	if failure_count >= settings.login_max_attempts:
		retry_after = max(await redis_store.get_login_failure_ttl(identifier, client_ip), 0)
		raise TooManyAttemptsError(retry_after=retry_after)


async def record_login_failure(identifier: str, client_ip: str, settings: BackendSettings) -> int:
	"""ログイン失敗を記録し、記録後の失敗回数を返す。"""
	return await redis_store.incr_login_failure(identifier, client_ip, settings.login_lock_window_seconds)


async def record_login_success(identifier: str, client_ip: str) -> None:
	"""ログイン成功時に失敗回数カウンタをリセットする。"""
	await redis_store.reset_login_failure(identifier, client_ip)


def _generate_token() -> str:
	return secrets.token_urlsafe(_TOKEN_URLSAFE_BYTES)


async def issue_email_verify_token(user: User, background: BackgroundTasks) -> None:
	"""新しいメール認証tokenを発行し、旧tokenを失効させ、送信を予約する。

	登録時・再送時の両方から呼ばれる共通関数（06_token_mail.md §8.1）。
	"""
	settings = get_backend_settings()
	token = _generate_token()
	await redis_store.replace_email_verify_token(token, user.id, ttl=settings.email_verify_ttl_seconds)
	await redis_store.mark_email_verify_sent(user.id, interval=settings.email_verify_resend_interval_seconds)
	background.add_task(
		mail_service.send_email_verification_mail,
		user.email,
		token,
		settings.email_verify_ttl_seconds // 3600,
	)


async def verify_email(token: str, db: AsyncSession) -> None:
	"""メール認証tokenをワンタイム消費し、email_verified_atを更新する。"""
	user_id = await redis_store.consume_email_verify_token(token)
	if user_id is None:
		raise InvalidVerifyTokenError()
	await user_repository.mark_email_verified(db, user_id)
	await db.commit()


async def resend_verification(email: str, background: BackgroundTasks, db: AsyncSession) -> None:
	"""認証メールを再送する。ユーザー不存在・認証済み・レート制限内でも例外を出さない。"""
	user = await user_repository.get_by_email(db, email)
	if user is None or user.email_verified_at is not None:
		return
	settings = get_backend_settings()
	sent = await redis_store.mark_email_verify_sent(user.id, interval=settings.email_verify_resend_interval_seconds)
	if not sent:
		# NX失敗＝直近送信済みで間隔内。再送しない。
		return
	await issue_email_verify_token(user, background)


async def request_password_reset(email: str, background: BackgroundTasks, db: AsyncSession) -> None:
	"""パスワードリセットtokenを発行する。ユーザー不存在でも例外を出さず202を維持する。"""
	user = await user_repository.get_by_email(db, email)
	if user is None:
		return
	settings = get_backend_settings()
	token = _generate_token()
	await redis_store.save_password_reset_token(token, user.id, ttl=settings.password_reset_ttl_seconds)
	background.add_task(
		mail_service.send_password_reset_mail,
		user.email,
		token,
		settings.password_reset_ttl_seconds // 60,
	)


async def reset_password(token: str, new_password: str, db: AsyncSession) -> None:
	"""パスワードリセットtokenを消費し、全セッション・全リフレッシュトークンを失効させた上でパスワードを更新する。

	Redisの失効が成功した後にのみDBを更新する（Redis失敗時はDB更新しない）。
	"""
	user_id = await redis_store.consume_password_reset_token(token)
	if user_id is None:
		raise InvalidResetTokenError()
	await redis_store.delete_all_sessions(user_id)
	await redis_store.revoke_all_refresh_tokens(user_id)

	password_hash = hash_password(new_password)
	await user_repository.update_password(db, user_id, password_hash)
	await db.commit()


_SQLSTATE_DUPLICATE_USERNAME = "P0001"
_SQLSTATE_DUPLICATE_EMAIL = "P0002"
_LOGIN_FAILURE_INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
_LOGIN_FAILURE_USER_INACTIVE = "USER_INACTIVE"
_LOGIN_FAILURE_EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"


def _duplicate_error_for(exc: DBAPIError) -> DuplicateUsernameError | DuplicateEmailError | None:
	"""sp_register_userの一意性違反（P0001/P0002）を409の業務エラーへ変換する。"""
	sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
	if sqlstate == _SQLSTATE_DUPLICATE_USERNAME:
		return DuplicateUsernameError()
	if sqlstate == _SQLSTATE_DUPLICATE_EMAIL:
		return DuplicateEmailError()
	return None


async def register(payload: RegisterRequest, background: BackgroundTasks, request: Request, db: AsyncSession) -> User:
	"""ユーザーを登録し、確認メール送信を予約する。認証状態は確立しない（01_post_auth_register.md）。"""
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
			raise
		raise duplicate from exc

	user = await user_repository.get_by_id(db, user_id)
	if user is None:
		raise ServiceUnavailableError()
	await issue_email_verify_token(user, background)
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


async def login(
	identifier: str,
	password: str,
	request: Request,
	response: Response,
	db: AsyncSession,
	strategy: AuthStrategy,
) -> LoginResult:
	"""認証を成立させ、AUTH_MODEに応じた認証状態を確立する（02_post_auth_login.md §6.2の判定順序）。"""
	settings = get_backend_settings()
	client_ip = resolve_client_ip(request, settings.trusted_proxy_cidrs).client_ip
	await ensure_login_not_rate_limited(identifier, client_ip, settings)

	user = await user_repository.get_by_login_identifier(db, identifier)
	# ユーザー不存在・OAuth専用アカウントでもダミーハッシュを検証し、応答時間差によるユーザー列挙を防ぐ。
	stored_hash = user.password_hash if user is not None and user.password_hash is not None else None
	password_matched = verify_password(password, stored_hash or get_dummy_password_hash())
	if user is None or stored_hash is None or not password_matched:
		await record_login_failure(identifier, client_ip, settings)
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
		raise InvalidCredentialsError()

	await record_login_success(identifier, client_ip)
	if not user.is_active:
		await _record_login_attempt(
			db,
			user,
			identifier,
			request,
			strategy.mode,
			client_ip,
			success=False,
			failure_reason=_LOGIN_FAILURE_USER_INACTIVE,
		)
		raise UserInactiveError()
	if user.email_verified_at is None:
		await _record_login_attempt(
			db,
			user,
			identifier,
			request,
			strategy.mode,
			client_ip,
			success=False,
			failure_reason=_LOGIN_FAILURE_EMAIL_NOT_VERIFIED,
		)
		raise EmailNotVerifiedError()

	login_result = await strategy.login(user, request, response)
	try:
		await _record_login_attempt(
			db, user, identifier, request, strategy.mode, client_ip, success=True, failure_reason=None
		)
	except Exception as exc:
		try:
			await strategy.rollback_login(user, login_result, response)
		except Exception as rollback_exc:
			logger.exception("login state rollback failed", extra={"user_id": str(user.id)})
			raise ServiceUnavailableError() from rollback_exc
		raise ServiceUnavailableError() from exc
	return login_result


async def logout(request: Request, response: Response, strategy: AuthStrategy) -> None:
	"""現在の認証状態を失効させる。未ログインでも例外を出さない冪等処理（03_post_auth_logout.md）。"""
	await strategy.logout(request, response)


async def refresh(request: Request, response: Response, strategy: AuthStrategy) -> LoginResult:
	"""access tokenを再発行する。モード差異はStrategyへ委譲する（06_post_auth_refresh.md §6.2）。

	sessionモードのStrategyは`NotSupportedInModeError`を送出し405となる。
	"""
	return await strategy.refresh(request, response)


def normalize_redirect_to(raw: str | None, settings: BackendSettings | None = None) -> str:
	config = settings or get_backend_settings()
	if not raw:
		return config.oauth_default_redirect_to
	parsed = urlsplit(raw)
	if (
		not raw.startswith("/")
		or raw.startswith("//")
		or parsed.scheme
		or parsed.netloc
		or len(raw) > config.oauth_redirect_to_max_length
		or "\\" in raw
		or any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw)
	):
		return config.oauth_default_redirect_to
	return raw


def _set_oauth_state_cookie(response: Response, state: str, settings: BackendSettings) -> None:
	options: dict[str, Any] = {
		"httponly": True,
		"secure": settings.cookie_secure,
		"samesite": settings.cookie_samesite,
		"path": "/api/auth/oauth",
		"max_age": settings.oauth_state_ttl_seconds,
	}
	if settings.cookie_domain:
		options["domain"] = settings.cookie_domain
	response.set_cookie(settings.cookie_name_oauth_state, state, **options)


def _delete_oauth_state_cookie(response: Response, settings: BackendSettings) -> None:
	options: dict[str, Any] = {
		"secure": settings.cookie_secure,
		"httponly": True,
		"samesite": settings.cookie_samesite,
		"path": "/api/auth/oauth",
	}
	if settings.cookie_domain:
		options["domain"] = settings.cookie_domain
	response.delete_cookie(settings.cookie_name_oauth_state, **options)


def _auth_strategy(settings: BackendSettings, strategy: Any | None) -> Any:
	if strategy is not None:
		return strategy
	configured = get_auth_strategy()
	if configured.mode == settings.auth_mode:
		return configured
	return SessionAuthStrategy(settings) if settings.auth_mode == "session" else JwtAuthStrategy(settings)


def _is_valid_jwt_login_result(login_result: Any) -> bool:
	if getattr(login_result, "auth_mode", None) != "jwt":
		return False
	for field in ("access_token", "refresh_token", "csrf_token"):
		value = getattr(login_result, field, None)
		if not isinstance(value, str) or not value:
			return False
	expires_in = getattr(login_result, "expires_in", None)
	return isinstance(expires_in, int) and not isinstance(expires_in, bool) and expires_in >= 1


async def _check_oauth_rate_limit(request: Request, scope: str, route: str, settings: BackendSettings) -> ClientIpInfo:
	client_info = resolve_client_ip(request, settings.trusted_proxy_cidrs)
	try:
		count = await redis_store.check_rate_limit(
			scope,
			client_info.client_ip,
			settings.rate_limit_oauth_max_requests,
			settings.rate_limit_oauth_window_seconds,
		)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if count > settings.rate_limit_oauth_max_requests:
		logger.warning(
			"OAuth rate limit rejected",
			extra={
				"operation": "rate_limit",
				"event": "rate_limit_rejected",
				"route": route,
				"scope": scope,
				"limit": settings.rate_limit_oauth_max_requests,
				"window": settings.rate_limit_oauth_window_seconds,
				"client_ip": client_info.client_ip,
				"proxy_peer_ip": client_info.proxy_peer_ip,
				"ip_source": client_info.ip_source,
				"request_id": _request_id(request),
			},
		)
		try:
			ttl = await redis_store.get_rate_limit_ttl(scope, client_info.client_ip)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		raise TooManyAttemptsError(retry_after=ttl if ttl > 0 else settings.rate_limit_oauth_window_seconds)
	return client_info


async def oauth_start(
	redirect_to: str | None,
	request: Request | Response | None = None,
	response: Response | None = None,
	*,
	settings: BackendSettings | None = None,
	provider: GoogleOAuthProvider | None = None,
) -> OAuthStartResult:
	config = settings or get_backend_settings()
	if isinstance(request, Request):
		await _check_oauth_rate_limit(request, _OAUTH_RATE_LIMIT_SCOPE["start"], "/api/auth/oauth/google", config)
	if isinstance(request, Response) and response is None:
		response = request
	redirect = normalize_redirect_to(redirect_to, config)
	state = secrets.token_urlsafe(32)
	code_verifier = secrets.token_urlsafe(64)
	nonce = secrets.token_urlsafe(32)
	code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
	try:
		await redis_store.save_oauth_state(state, redirect, code_verifier, nonce, config.oauth_state_ttl_seconds)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if response is not None:
		_set_oauth_state_cookie(response, state, config)
	oauth_provider = provider or GoogleOAuthProvider(config)
	return OAuthStartResult(authorize_url=oauth_provider.build_authorize_url(state, code_challenge, nonce), state=state)


async def _resolve_or_create_user(db: AsyncSession, userinfo: GoogleUserInfo) -> User:
	account = await oauth_account_repository.get_by_provider_identity(db, "google", userinfo.sub)
	if account is not None:
		user = account.user or await user_repository.get_by_id(db, account.user_id)
		if user is None:
			raise OAuthFailedError()
		if not user.is_active:
			raise UserInactiveError()
		return user

	existing = await user_repository.get_by_email(db, userinfo.email)
	if existing is not None:
		if not userinfo.email_verified:
			raise OAuthEmailUnverifiedError()
		if not existing.is_active:
			raise UserInactiveError()
		await oauth_account_repository.upsert(db, existing.id, "google", userinfo.sub)
		if existing.email_verified_at is None:
			await user_repository.mark_email_verified(db, existing.id)
		await db.commit()
		return existing

	if not userinfo.email_verified:
		raise OAuthEmailUnverifiedError()
	username = f"google_{hashlib.sha256(userinfo.sub.encode()).hexdigest()[:16]}"
	user_id = await user_repository.create(db, username, userinfo.email, None)
	await oauth_account_repository.upsert(db, user_id, "google", userinfo.sub)
	await user_repository.mark_email_verified(db, user_id)
	if userinfo.given_name is not None or userinfo.family_name is not None:
		await user_repository.update_profile(db, user_id, userinfo.family_name, userinfo.given_name, None, None, None)
	await db.commit()
	user = await user_repository.get_by_id(db, user_id)
	if user is None:
		raise OAuthFailedError()
	if not user.is_active:
		raise UserInactiveError()
	return user


async def resolve_or_create_user(
	db: AsyncSession,
	sub: str,
	email: str,
	email_verified: bool,
	given_name: str | None,
	family_name: str | None,
) -> User:
	return await _resolve_or_create_user(db, GoogleUserInfo(sub, email, email_verified, given_name, family_name))


def _request_id(request: Request) -> str | None:
	request_state = getattr(request, "state", None)
	value = getattr(request_state, "request_id", None)
	return value if isinstance(value, str) else None


def _log_login_history_write_failed(request: Request, user: User, client_info: ClientIpInfo) -> None:
	logger.warning(
		"OAuth login history write failed",
		extra={
			"operation": "oauth_login",
			"event": "login_history_write_failed",
			"user_id": str(user.id),
			"login_method": "oauth_google",
			"client_ip": client_info.client_ip,
			"proxy_peer_ip": client_info.proxy_peer_ip,
			"ip_source": client_info.ip_source,
			"request_id": _request_id(request),
		},
	)


def _log_auth_state_revoke_failed(
	request: Request,
	user: User,
	operation: str,
	login_result: Any,
	client_info: ClientIpInfo,
) -> None:
	logger.error(
		"OAuth authentication state revoke failed",
		extra={
			"operation": operation,
			"event": "auth_state_revoke_failed",
			"user_id": str(user.id),
			"deleted_session_count": 0 if getattr(login_result, "session_id", None) is None else 1,
			"deleted_refresh_count": 0 if getattr(login_result, "refresh_token", None) is None else 1,
			"client_ip": client_info.client_ip,
			"proxy_peer_ip": client_info.proxy_peer_ip,
			"ip_source": client_info.ip_source,
			"request_id": _request_id(request),
		},
	)


async def _record_oauth_login(
	db: AsyncSession, user: User, request: Request, client_info: ClientIpInfo | None = None
) -> None:
	resolved_ip = client_info or resolve_client_ip(request, get_backend_settings().trusted_proxy_cidrs)
	await login_history_repository.create(
		db,
		user_id=user.id,
		login_identifier=user.email,
		login_method="oauth_google",
		ip_address=resolved_ip.client_ip,
		user_agent=request.headers.get("user-agent"),
		success=True,
		failure_reason=None,
	)
	await db.commit()


async def _rollback_oauth_login(
	strategy: Any,
	user: User,
	login_result: Any,
	response: Response,
	settings: BackendSettings,
	*,
	clear_state_cookie: bool,
	request: Request,
	client_info: ClientIpInfo,
	operation: str,
) -> None:
	try:
		rollback = getattr(strategy, "rollback_login", None)
		if rollback is None:
			raise RuntimeError("auth strategy does not support login rollback")
		await rollback(user, login_result, response)
	except Exception:
		_log_auth_state_revoke_failed(request, user, operation, login_result, client_info)
		raise
	finally:
		if clear_state_cookie:
			_delete_oauth_state_cookie(response, settings)


async def oauth_callback(
	code: str | None,
	state: str | None,
	state_cookie: str | None,
	request: Request,
	response: Response,
	db: AsyncSession | None = None,
	*,
	settings: BackendSettings | None = None,
	provider: GoogleOAuthProvider | None = None,
	strategy: Any | None = None,
) -> OAuthCallbackResult:
	config = settings or get_backend_settings()
	client_info = await _check_oauth_rate_limit(
		request, _OAUTH_RATE_LIMIT_SCOPE["callback"], "/api/auth/oauth/google/callback", config
	)
	if not state or not state_cookie or not secrets.compare_digest(state, state_cookie):
		raise InvalidStateError()
	try:
		state_data = await redis_store.consume_oauth_state(state)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if state_data is None:
		raise InvalidStateError()
	if not code or db is None:
		raise OAuthFailedError()
	oauth_provider = provider or GoogleOAuthProvider(config)
	tokens = await oauth_provider.exchange_code(code, state_data.code_verifier)
	claims = await oauth_provider.verify_id_token(tokens.id_token, state_data.nonce)
	userinfo = await oauth_provider.fetch_userinfo(tokens.access_token)
	if not secrets.compare_digest(claims.sub, userinfo.sub):
		raise OAuthFailedError()
	user = await _resolve_or_create_user(db, userinfo)
	if not user.is_active:
		raise UserInactiveError()
	if config.auth_mode == "session":
		auth_strategy = _auth_strategy(config, strategy)
		login_result = await auth_strategy.login(user, request, response)
		try:
			await _record_oauth_login(db, user, request, client_info)
		except Exception as exc:
			_log_login_history_write_failed(request, user, client_info)
			try:
				await _rollback_oauth_login(
					auth_strategy,
					user,
					login_result,
					response,
					config,
					clear_state_cookie=True,
					request=request,
					client_info=client_info,
					operation="oauth_callback_session",
				)
			except Exception as rollback_exc:
				raise ServiceUnavailableError() from rollback_exc
			raise ServiceUnavailableError() from exc
		_delete_oauth_state_cookie(response, config)
		return OAuthCallbackResult(auth_mode="session", redirect_to=state_data.redirect_to)

	handoff_code = secrets.token_urlsafe(32)
	try:
		await redis_store.save_oauth_handoff(
			handoff_code, user.id, state_data.redirect_to, config.oauth_handoff_ttl_seconds
		)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	_delete_oauth_state_cookie(response, config)
	return OAuthCallbackResult(auth_mode="jwt", redirect_to=state_data.redirect_to, handoff_code=handoff_code)


async def oauth_exchange(
	code: str,
	request: Request,
	response: Response,
	db: AsyncSession | None = None,
	*,
	settings: BackendSettings | None = None,
	strategy: Any | None = None,
) -> OAuthExchangeResponse:
	config = settings or get_backend_settings()
	client_info = await _check_oauth_rate_limit(
		request, _OAUTH_RATE_LIMIT_SCOPE["exchange"], "/api/auth/oauth/exchange", config
	)
	if config.auth_mode != "jwt":
		raise NotSupportedInModeError()
	try:
		handoff = await redis_store.consume_oauth_handoff(code)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if handoff is None:
		raise OAuthHandoffInvalidError()
	if db is None:
		raise OAuthFailedError()
	user = await user_repository.get_by_id(db, handoff.user_id)
	if user is None or not user.is_active:
		raise UserInactiveError()
	auth_strategy = _auth_strategy(config, strategy)
	login_result = await auth_strategy.login(user, request, response)
	if not _is_valid_jwt_login_result(login_result):
		try:
			await _rollback_oauth_login(
				auth_strategy,
				user,
				login_result,
				response,
				config,
				clear_state_cookie=False,
				request=request,
				client_info=client_info,
				operation="oauth_exchange_invalid_login_result",
			)
		except Exception as rollback_exc:
			raise ServiceUnavailableError() from rollback_exc
		raise OAuthFailedError()
	try:
		await _record_oauth_login(db, user, request, client_info)
	except Exception as exc:
		_log_login_history_write_failed(request, user, client_info)
		try:
			await _rollback_oauth_login(
				auth_strategy,
				user,
				login_result,
				response,
				config,
				clear_state_cookie=False,
				request=request,
				client_info=client_info,
				operation="oauth_exchange_login_history",
			)
		except Exception as rollback_exc:
			raise ServiceUnavailableError() from rollback_exc
		raise ServiceUnavailableError() from exc
	return OAuthExchangeResponse(
		access_token=login_result.access_token,
		token_type="bearer",
		expires_in=login_result.expires_in,
		redirect_to=handoff.redirect_to,
	)

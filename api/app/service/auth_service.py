"""ログイン失敗レート制限（ブルートフォース対策）と、メール認証・パスワードリセットのトークン発行・消費オーケストレーション。

参照設計書: docs/detailed_design/auth/06_token_mail.md
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.factory import get_auth_strategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.auth.oauth import GoogleOAuthProvider, GoogleUserInfo
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import (
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
from app.core.security import hash_password
from app.models.user import User
from app.repository import login_history_repository, oauth_account_repository, redis_store, user_repository
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
		raise TooManyAttemptsError()


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


async def _check_oauth_rate_limit(request: Request, scope: str, settings: BackendSettings) -> None:
	client_ip = request.client.host if request.client is not None else "unknown"
	try:
		count = await redis_store.check_rate_limit(
			scope, client_ip, settings.rate_limit_oauth_max_requests, settings.rate_limit_oauth_window_seconds
		)
	except Exception as exc:
		raise ServiceUnavailableError() from exc
	if count > settings.rate_limit_oauth_max_requests:
		logger.warning(
			"OAuth rate limit rejected",
			extra={"operation": "rate_limit", "event": "rate_limit_rejected"},
		)
		raise TooManyAttemptsError()


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
		await _check_oauth_rate_limit(request, _OAUTH_RATE_LIMIT_SCOPE["start"], config)
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


async def _record_oauth_login(db: AsyncSession, user: User, request: Request) -> None:
	client_ip = request.client.host if request.client is not None else None
	await login_history_repository.create(
		db,
		user_id=user.id,
		login_identifier=user.email,
		login_method="oauth_google",
		ip_address=client_ip,
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
) -> None:
	try:
		rollback = getattr(strategy, "rollback_login", None)
		if rollback is None:
			raise RuntimeError("auth strategy does not support login rollback")
		await rollback(user, login_result, response)
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
	await _check_oauth_rate_limit(request, _OAUTH_RATE_LIMIT_SCOPE["callback"], config)
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
			await _record_oauth_login(db, user, request)
		except Exception as exc:
			try:
				await _rollback_oauth_login(
					auth_strategy, user, login_result, response, config, clear_state_cookie=True
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
	await _check_oauth_rate_limit(request, _OAUTH_RATE_LIMIT_SCOPE["exchange"], config)
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
	try:
		await _record_oauth_login(db, user, request)
	except Exception as exc:
		try:
			await _rollback_oauth_login(auth_strategy, user, login_result, response, config, clear_state_cookie=False)
		except Exception as rollback_exc:
			raise ServiceUnavailableError() from rollback_exc
		raise ServiceUnavailableError() from exc
	if login_result.access_token is None or login_result.expires_in is None:
		raise OAuthFailedError()
	return OAuthExchangeResponse(
		access_token=login_result.access_token,
		token_type="bearer",
		expires_in=login_result.expires_in,
		redirect_to=handoff.redirect_to,
	)

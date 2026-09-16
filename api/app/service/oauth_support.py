"""OAuthサービスが共有するCookie・レート制限・認証方式補助。"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request, Response

from app.core.client_ip import ClientIpInfo, resolve_client_ip
from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import ServiceUnavailableError, TooManyAttemptsError
from app.models.user import User
from app.repository import login_history_repository, redis_store
from app.service.auth_logging import log_auth_state_revoke_failed, log_login_history_write_failed, request_id

logger = logging.getLogger("app.oauth")
OAUTH_RATE_LIMIT_SCOPE = {"start": "oauth_start", "callback": "oauth_callback", "exchange": "oauth_exchange"}


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


def set_oauth_state_cookie(response: Response, state: str, settings: BackendSettings) -> None:
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


def delete_oauth_state_cookie(response: Response, settings: BackendSettings) -> None:
	options: dict[str, Any] = {
		"secure": settings.cookie_secure,
		"httponly": True,
		"samesite": settings.cookie_samesite,
		"path": "/api/auth/oauth",
	}
	if settings.cookie_domain:
		options["domain"] = settings.cookie_domain
	response.delete_cookie(settings.cookie_name_oauth_state, **options)


def is_valid_jwt_login_result(login_result: Any) -> bool:
	if getattr(login_result, "auth_mode", None) != "jwt":
		return False
	for field in ("access_token", "refresh_token", "csrf_token"):
		value = getattr(login_result, field, None)
		if not isinstance(value, str) or not value:
			return False
	expires_in = getattr(login_result, "expires_in", None)
	return isinstance(expires_in, int) and not isinstance(expires_in, bool) and expires_in >= 1


async def check_oauth_rate_limit(request: Request, scope: str, route: str, settings: BackendSettings) -> ClientIpInfo:
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
				"request_id": request_id(request),
			},
		)
		try:
			ttl = await redis_store.get_rate_limit_ttl(scope, client_info.client_ip)
		except Exception as exc:
			raise ServiceUnavailableError() from exc
		raise TooManyAttemptsError(retry_after=ttl if ttl > 0 else settings.rate_limit_oauth_window_seconds)
	return client_info


async def record_oauth_login(db: Any, user: User, request: Request, client_info: ClientIpInfo | None = None) -> None:
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


async def rollback_oauth_login(
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
		log_auth_state_revoke_failed(request, user, operation, client_info)
		raise
	finally:
		if clear_state_cookie:
			delete_oauth_state_cookie(response, settings)


async def complete_oauth_session_login(
	db: Any,
	user: User,
	request: Request,
	response: Response,
	settings: BackendSettings,
	client_info: ClientIpInfo,
	strategy: Any,
	login_result: Any,
	record_login: Any,
) -> None:
	try:
		await record_login(db, user, request, client_info)
	except Exception as exc:
		log_login_history_write_failed(request, user, client_info)
		try:
			await rollback_oauth_login(
				strategy,
				user,
				login_result,
				response,
				settings,
				clear_state_cookie=True,
				request=request,
				client_info=client_info,
				operation="oauth_callback_session",
			)
		except Exception as rollback_exc:
			raise ServiceUnavailableError() from rollback_exc
		raise ServiceUnavailableError() from exc
	delete_oauth_state_cookie(response, settings)

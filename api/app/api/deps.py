from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import (
	CsrfInvalidError,
	ForbiddenError,
	SessionExpiredError,
	UnauthenticatedError,
	UserInactiveError,
)
from app.db import get_db_session
from app.redis_client import get_redis_client
from app.repository import project_member_repository, project_repository, user_repository
from app.repository.session_repository import RedisSessionInterface, SessionRepository
from app.schemas.auth import CurrentUser
from app.service.auth_strategy import AuthContext, AuthStrategy
from app.service.auth_strategy import get_auth_strategy as build_auth_strategy
from app.service.authorization_service import authorize_project_member, authorize_project_owner
from app.service.session_auth_service import SessionAuthContext, SessionAuthService


def get_session_auth_service(
	redis: RedisSessionInterface = Depends(get_redis_client),
	settings: BackendSettings = Depends(get_backend_settings),
) -> SessionAuthService:
	return SessionAuthService(SessionRepository(redis, settings.redis_key_prefix), settings)


async def get_db() -> AsyncIterator[AsyncSession]:
	async for session in get_db_session():
		yield session


def get_auth_strategy(settings: BackendSettings = Depends(get_backend_settings)) -> AuthStrategy:
	return build_auth_strategy(settings)


async def get_current_user(
	request: Request,
	strategy: AuthStrategy | SessionAuthService = Depends(build_auth_strategy),
	db: AsyncSession = Depends(get_db_session),
) -> CurrentUser | SessionAuthContext:
	if isinstance(strategy, SessionAuthService):
		context = await strategy.authenticate(request)
		if context is None:
			if strategy.has_session_cookie(request):
				raise SessionExpiredError()
			raise UnauthenticatedError()
		return context

	context: AuthContext | None = await strategy.authenticate(request)
	if context is None:
		raise UnauthenticatedError()

	user = await user_repository.get_by_id(db, context.user_id)
	if user is None:
		raise UnauthenticatedError()
	if not user.is_active:
		raise UserInactiveError()

	return CurrentUser(
		id=user.id,
		username=user.username,
		role=user.role,
		is_active=user.is_active,
		email_verified_at=user.email_verified_at,
	)


get_current_session = get_current_user


async def get_current_user_optional(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	db: AsyncSession = Depends(get_db_session),
) -> CurrentUser | None:
	try:
		result = await get_current_user(request, strategy, db)
		if isinstance(result, CurrentUser):
			return result
		raise UnauthenticatedError()
	except UnauthenticatedError:
		return None
	except UserInactiveError:
		return None


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
	if user.role != "admin":
		raise ForbiddenError()
	return user


async def require_project_member(
	project_id: UUID,
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
) -> Any:
	project = await project_repository.get_by_id(db, project_id)
	is_member = user.role == "admin" or await project_member_repository.exists(db, project_id, user.id)
	return authorize_project_member(user, project, is_member)


async def require_project_owner(
	project: Any = Depends(require_project_member),
	user: CurrentUser = Depends(get_current_user),
) -> Any:
	return authorize_project_owner(user, project, is_member=True)


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
OAUTH_CALLBACK_PATH = "/api/auth/oauth/google/callback"
CSRF_EXEMPT_PATHS = frozenset({OAUTH_CALLBACK_PATH, "/api/auth/login", "/api/auth/register"})


def _settings(settings: BackendSettings | None) -> BackendSettings:
	return settings or get_backend_settings()


def _is_oauth_callback(request: Request) -> bool:
	return request.url.path == OAUTH_CALLBACK_PATH


def _allowed_origin(origin: str, settings: BackendSettings) -> bool:
	return origin in settings.cors_allow_origins


def _referer_origin(referer: str) -> str | None:
	parsed = urlsplit(referer)
	if parsed.scheme not in {"http", "https"} or not parsed.netloc:
		return None
	return f"{parsed.scheme}://{parsed.netloc}"


async def verify_origin(request: Request, settings: BackendSettings | None = None) -> None:
	resolved_settings = _settings(settings)
	if _is_oauth_callback(request):
		return

	origin = request.headers.get("origin")
	if origin is not None:
		if _allowed_origin(origin, resolved_settings):
			return
		raise CsrfInvalidError()

	if (
		request.url.scheme == "https"
		and resolved_settings.csrf_trust_referer_on_https
		and (referer := request.headers.get("referer"))
		and (referer_origin := _referer_origin(referer))
		and _allowed_origin(referer_origin, resolved_settings)
	):
		return
	raise CsrfInvalidError()


def _is_csrf_exempt(request: Request) -> bool:
	return request.method.upper() in SAFE_METHODS or request.url.path in CSRF_EXEMPT_PATHS


def _strategy_mode(strategy: object | None, settings: BackendSettings) -> str:
	return str(getattr(strategy, "mode", None) or getattr(strategy, "auth_mode", None) or settings.auth_mode)


async def _session_csrf_token(redis_client: Any, session_id: str, settings: BackendSettings) -> str | None:
	get_token = getattr(redis_client, "get_csrf_token", None)
	if get_token is not None:
		return cast(str | None, await get_token(session_id))
	return cast(str | None, await redis_client.get(f"{settings.redis_key_prefix}csrf:{session_id}"))


async def verify_csrf(
	request: Request,
	strategy: object | None = None,
	redis_client: Any | None = None,
	settings: BackendSettings | None = None,
) -> None:
	if _is_csrf_exempt(request):
		return

	resolved_settings = _settings(settings)
	cookie_token = request.cookies.get(resolved_settings.cookie_name_csrf)
	header_token = request.headers.get("X-CSRF-Token")
	if not cookie_token or not header_token:
		raise CsrfInvalidError()

	if _strategy_mode(strategy, resolved_settings) == "jwt":
		if secrets.compare_digest(cookie_token, header_token):
			return
		raise CsrfInvalidError()

	session_id = request.cookies.get(resolved_settings.cookie_name_session)
	if not session_id:
		raise CsrfInvalidError()
	client = redis_client or get_redis_client()
	stored_token = await _session_csrf_token(client, session_id, resolved_settings)
	if (
		stored_token
		and secrets.compare_digest(cookie_token, stored_token)
		and secrets.compare_digest(cookie_token, header_token)
	):
		return
	raise CsrfInvalidError()

import secrets
from urllib.parse import urlparse
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthStrategy
from app.auth.factory import get_auth_strategy
from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import CsrfInvalidError, ForbiddenError, NotFoundError, UnauthenticatedError, UserInactiveError
from app.db import get_db_session
from app.models.project import Project
from app.repository import project_repository, redis_store, user_repository
from app.schemas.auth import CurrentUser


async def get_current_user(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	db: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
	context = await strategy.authenticate(request)
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


async def get_current_user_optional(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	db: AsyncSession = Depends(get_db_session),
) -> CurrentUser | None:
	try:
		return await get_current_user(request, strategy, db)
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
	db: AsyncSession = Depends(get_db_session),
) -> Project:
	project = await project_repository.get_by_id(db, project_id)
	if project is None:
		raise NotFoundError()
	if user.role == "admin":
		return project
	if not await project_repository_member_exists(db, project_id, user.id):
		raise NotFoundError()
	return project


async def project_repository_member_exists(db: AsyncSession, project_id: UUID, user_id: UUID) -> bool:
	from app.repository import project_member_repository

	return await project_member_repository.exists(db, project_id, user_id)


async def require_project_owner(
	project: Project = Depends(require_project_member), user: CurrentUser = Depends(get_current_user)
) -> Project:
	if user.role != "admin" and project.owner_id != user.id:
		raise ForbiddenError()
	return project


async def verify_origin(request: Request, settings: BackendSettings = Depends(get_backend_settings)) -> None:
	origin = request.headers.get("origin")
	if origin is None and request.url.scheme == "https" and settings.csrf_trust_referer_on_https:
		origin = _origin_from_referer(request.headers.get("referer"))
	if origin is None or origin not in settings.cors_allow_origins:
		raise CsrfInvalidError()


def _origin_from_referer(referer: str | None) -> str | None:
	if not referer:
		return None
	parsed = urlparse(referer)
	if not parsed.scheme or not parsed.netloc:
		return None
	return f"{parsed.scheme}://{parsed.netloc}"


async def verify_csrf(
	request: Request,
	strategy: AuthStrategy = Depends(get_auth_strategy),
	settings: BackendSettings = Depends(get_backend_settings),
) -> None:
	if strategy.mode == "jwt":
		return
	header = request.headers.get("x-csrf-token")
	if not header:
		raise CsrfInvalidError()
	session_id = request.cookies.get(settings.cookie_name_session)
	if not session_id:
		raise CsrfInvalidError()
	cookie_token = await redis_store.get_csrf_token(session_id)
	if cookie_token is None or not secrets.compare_digest(cookie_token, header):
		raise CsrfInvalidError()

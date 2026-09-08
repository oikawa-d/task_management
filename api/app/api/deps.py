from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import ForbiddenError, UnauthenticatedError, UserInactiveError
from app.db import get_db_session
from app.repository import user_repository
from app.schemas.auth import CurrentUser
from app.service.auth_strategy import AuthContext, AuthStrategy
from app.service.auth_strategy import get_auth_strategy as build_auth_strategy


def get_auth_strategy(settings: BackendSettings = Depends(get_backend_settings)) -> AuthStrategy:
	return build_auth_strategy(settings)


async def get_current_user(
	request: Request,
	strategy: AuthStrategy = Depends(build_auth_strategy),
	db: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
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

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import ForbiddenError, SessionExpiredError, UnauthenticatedError, UserInactiveError
from app.db import get_db_session
from app.redis_client import get_redis_client
from app.repository import user_repository
from app.repository.session_repository import RedisSessionInterface, SessionRepository
from app.schemas.auth import CurrentUser
from app.service.auth_strategy import AuthContext, AuthStrategy
from app.service.auth_strategy import get_auth_strategy as build_auth_strategy
from app.service.session_auth_service import SessionAuthContext, SessionAuthService


def get_session_auth_service(
	redis: RedisSessionInterface = Depends(get_redis_client),
	settings: BackendSettings = Depends(get_backend_settings),
) -> SessionAuthService:
	return SessionAuthService(SessionRepository(redis, settings.redis_key_prefix), settings)


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

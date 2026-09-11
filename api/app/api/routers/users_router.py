from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BackendSettings, get_backend_settings
from app.core.deps import get_current_user, verify_csrf_if_session, verify_origin
from app.db import get_db_session
from app.schemas.auth import CurrentUser
from app.schemas.user import (
	LoginHistoryListResponse,
	PasswordChangeRequest,
	UserProfileResponse,
	UserProfileUpdateRequest,
)
from app.service import user_service

router = APIRouter(tags=["users"])


@router.get("/api/users/me", response_model=UserProfileResponse)
async def get_my_profile(
	response: Response,
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> UserProfileResponse:
	response.headers["Cache-Control"] = "no-store"
	return await user_service.get_profile(current_user, db)


@router.patch("/api/users/me", response_model=UserProfileResponse)
async def patch_my_profile(
	payload: UserProfileUpdateRequest,
	response: Response,
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf_if_session),
) -> UserProfileResponse:
	response.headers["Cache-Control"] = "no-store"
	return await user_service.update_profile(current_user, payload, db)


@router.put("/api/users/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_password(
	payload: PasswordChangeRequest,
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf_if_session),
) -> Response:
	await user_service.change_password(current_user, payload, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/users/me/login-history", response_model=LoginHistoryListResponse)
async def get_my_login_history(
	response: Response,
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
) -> LoginHistoryListResponse:
	response.headers["Cache-Control"] = "no-store"
	return await user_service.get_login_history(current_user, db, limit=settings.login_history_list_limit)

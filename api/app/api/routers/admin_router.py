from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin, verify_csrf, verify_origin
from app.db import get_db_session
from app.schemas.admin import (
	AdminLoginHistoryListResponse,
	AdminLoginHistoryQuery,
	AdminProjectListQuery,
	AdminProjectListResponse,
	AdminUserDetailResponse,
	AdminUserListQuery,
	AdminUserListResponse,
	AdminUserRoleUpdateRequest,
	AdminUserStatusUpdateRequest,
)
from app.schemas.auth import CurrentUser
from app.service import admin_login_history_service, admin_project_service, admin_user_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
	query: AdminUserListQuery = Depends(),
	user: CurrentUser = Depends(require_admin),
	db: AsyncSession = Depends(get_db_session),
) -> AdminUserListResponse:
	return await admin_user_service.list_users(query, db)


@router.patch("/users/{user_id}/role", response_model=AdminUserDetailResponse)
async def patch_admin_user_role(
	user_id: UUID,
	payload: AdminUserRoleUpdateRequest,
	actor: CurrentUser = Depends(require_admin),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
	db: AsyncSession = Depends(get_db_session),
) -> AdminUserDetailResponse:
	return await admin_user_service.change_role(actor, user_id, payload.role, db)


@router.patch("/users/{user_id}/status", response_model=AdminUserDetailResponse)
async def patch_admin_user_status(
	user_id: UUID,
	payload: AdminUserStatusUpdateRequest,
	actor: CurrentUser = Depends(require_admin),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
	db: AsyncSession = Depends(get_db_session),
) -> AdminUserDetailResponse:
	return await admin_user_service.change_status(actor, user_id, payload.is_active, db)


@router.post("/users/{user_id}/force-logout", status_code=status.HTTP_204_NO_CONTENT)
async def post_admin_user_force_logout(
	user_id: UUID,
	actor: CurrentUser = Depends(require_admin),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
	db: AsyncSession = Depends(get_db_session),
) -> Response:
	await admin_user_service.force_logout(actor, user_id, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects", response_model=AdminProjectListResponse)
async def list_admin_projects(
	query: AdminProjectListQuery = Depends(),
	user: CurrentUser = Depends(require_admin),
	db: AsyncSession = Depends(get_db_session),
) -> AdminProjectListResponse:
	return await admin_project_service.list_projects(query, db)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_project(
	project_id: UUID,
	actor: CurrentUser = Depends(require_admin),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
	db: AsyncSession = Depends(get_db_session),
) -> Response:
	await admin_project_service.deactivate_project(actor, project_id, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/login-history", response_model=AdminLoginHistoryListResponse)
async def list_admin_login_history(
	query: AdminLoginHistoryQuery = Depends(),
	user: CurrentUser = Depends(require_admin),
	db: AsyncSession = Depends(get_db_session),
) -> AdminLoginHistoryListResponse:
	return await admin_login_history_service.search(query, db)

"""管理者向けのユーザー・プロジェクト・ログイン履歴管理エンドポイント。

全エンドポイントは`require_admin`により`role == "admin"`のユーザーのみ許可し、
それ以外は403 FORBIDDENを返す。更新系エンドポイントはOrigin検証・CSRF検証も課す。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
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
	"""GET /api/admin/users: ユーザー一覧を検索条件付きで取得する。

	認可: 管理者ロールのみ（`require_admin`、満たさない場合403 FORBIDDEN）。

	Args:
		query: 検索・ページング条件。
		user: 認可チェック済みの実行ユーザー（未認証は401 UNAUTHENTICATED）。
		db: DBセッション。

	Returns:
		200 OKでユーザー一覧を返す。
	"""
	return await admin_user_service.list_users(query, db)


@router.patch("/users/{user_id}/role", response_model=AdminUserDetailResponse)
async def patch_admin_user_role(
	user_id: UUID,
	payload: AdminUserRoleUpdateRequest,
	request: Request,
	actor: CurrentUser = Depends(require_admin),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
	db: AsyncSession = Depends(get_db_session),
) -> AdminUserDetailResponse:
	"""PATCH /api/admin/users/{user_id}/role: 対象ユーザーのロールを変更する。

	認可: 管理者ロールのみ。Origin検証・CSRF検証も必須（不正時403 CSRF_INVALID）。

	Args:
		user_id: 変更対象ユーザーのID。
		payload: 変更後ロールを含むリクエストボディ。
		request: リクエストID取得のためのRequest。
		actor: 操作を行う管理者ユーザー。
		db: DBセッション。

	Returns:
		200 OKで更新後のユーザー詳細を返す。

	Raises:
		NotFoundError: 対象ユーザーが存在しない場合（404 NOT_FOUND）。
		SelfModificationError: 自分自身のロールを変更しようとした場合（409 SELF_MODIFICATION_NOT_ALLOWED）。
		LastAdminRequiredError: 最後の管理者のロールを剥奪しようとした場合（409 LAST_ADMIN_REQUIRED）。
	"""
	return await admin_user_service.change_role(actor, user_id, payload.role, db, request_id=request.state.request_id)


@router.patch("/users/{user_id}/status", response_model=AdminUserDetailResponse)
async def patch_admin_user_status(
	user_id: UUID,
	payload: AdminUserStatusUpdateRequest,
	request: Request,
	actor: CurrentUser = Depends(require_admin),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
	db: AsyncSession = Depends(get_db_session),
) -> AdminUserDetailResponse:
	"""PATCH /api/admin/users/{user_id}/status: 対象ユーザーの有効/無効を切り替える。

	認可: 管理者ロールのみ。Origin検証・CSRF検証も必須（不正時403 CSRF_INVALID）。

	Args:
		user_id: 変更対象ユーザーのID。
		payload: 変更後の有効状態を含むリクエストボディ。
		request: リクエストID取得のためのRequest。
		actor: 操作を行う管理者ユーザー。
		db: DBセッション。

	Returns:
		200 OKで更新後のユーザー詳細を返す。

	Raises:
		NotFoundError: 対象ユーザーが存在しない場合（404 NOT_FOUND）。
		SelfModificationError: 自分自身を無効化しようとした場合（409 SELF_MODIFICATION_NOT_ALLOWED）。
		LastAdminRequiredError: 最後の管理者を無効化しようとした場合（409 LAST_ADMIN_REQUIRED）。
	"""
	return await admin_user_service.change_status(
		actor, user_id, payload.is_active, db, request_id=request.state.request_id
	)


@router.post("/users/{user_id}/force-logout", status_code=status.HTTP_204_NO_CONTENT)
async def post_admin_user_force_logout(
	user_id: UUID,
	request: Request,
	actor: CurrentUser = Depends(require_admin),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
	db: AsyncSession = Depends(get_db_session),
) -> Response:
	"""POST /api/admin/users/{user_id}/force-logout: 対象ユーザーの認証状態を強制的に失効させる。

	認可: 管理者ロールのみ。Origin検証・CSRF検証も必須（不正時403 CSRF_INVALID）。
	sessionモードならセッションを、jwtモードならrefresh tokenファミリーを失効させる。

	Args:
		user_id: 強制ログアウト対象ユーザーのID。
		request: リクエストID取得のためのRequest。
		actor: 操作を行う管理者ユーザー。
		db: DBセッション。

	Returns:
		204 No Contentを返す。
	"""
	await admin_user_service.force_logout(actor, user_id, db, request_id=request.state.request_id)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects", response_model=AdminProjectListResponse)
async def list_admin_projects(
	query: AdminProjectListQuery = Depends(),
	user: CurrentUser = Depends(require_admin),
	db: AsyncSession = Depends(get_db_session),
) -> AdminProjectListResponse:
	"""GET /api/admin/projects: プロジェクト一覧を検索条件付きで取得する。

	認可: 管理者ロールのみ（`require_admin`、満たさない場合403 FORBIDDEN）。

	Args:
		query: 検索・ページング条件。
		user: 認可チェック済みの実行ユーザー。
		db: DBセッション。

	Returns:
		200 OKでプロジェクト一覧を返す。
	"""
	return await admin_project_service.list_projects(query, db)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_project(
	project_id: UUID,
	request: Request,
	actor: CurrentUser = Depends(require_admin),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
	db: AsyncSession = Depends(get_db_session),
) -> Response:
	"""DELETE /api/admin/projects/{project_id}: プロジェクトを無効化する。

	認可: 管理者ロールのみ。Origin検証・CSRF検証も必須（不正時403 CSRF_INVALID）。
	物理削除ではなく無効化のため、一覧からは除外されるが履歴データは保持される。

	Args:
		project_id: 無効化対象プロジェクトのID。
		request: リクエストID取得のためのRequest。
		actor: 操作を行う管理者ユーザー。
		db: DBセッション。

	Returns:
		204 No Contentを返す。

	Raises:
		NotFoundError: 対象プロジェクトが存在しない場合（404 NOT_FOUND）。
	"""
	await admin_project_service.deactivate_project(actor, project_id, db, request_id=request.state.request_id)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/login-history", response_model=AdminLoginHistoryListResponse)
async def list_admin_login_history(
	query: AdminLoginHistoryQuery = Depends(),
	user: CurrentUser = Depends(require_admin),
	db: AsyncSession = Depends(get_db_session),
) -> AdminLoginHistoryListResponse:
	"""GET /api/admin/login-history: 全ユーザーのログイン履歴を検索条件付きで取得する。

	認可: 管理者ロールのみ（`require_admin`、満たさない場合403 FORBIDDEN）。

	Args:
		query: 検索・ページング条件。
		user: 認可チェック済みの実行ユーザー。
		db: DBセッション。

	Returns:
		200 OKでログイン履歴一覧を返す。
	"""
	return await admin_login_history_service.search(query, db)

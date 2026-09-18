"""ログインユーザー自身のプロフィール・パスワード・ログイン履歴のエンドポイント。

全エンドポイントは認証必須で、更新系はOrigin検証・CSRF検証も課す。
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BackendSettings, get_backend_settings
from app.core.deps import get_current_user, verify_csrf_if_session, verify_origin_if_session
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
	"""GET /api/users/me: ログインユーザー自身のプロフィールを取得する。

	認可: 認証必須（未認証は401 UNAUTHENTICATED）。レスポンスは`Cache-Control: no-store`とする。

	Args:
		response: no-storeヘッダ設定先のResponse。
		current_user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKでプロフィールを返す。

	Raises:
		NotFoundError: ユーザーが既に削除されている等で見つからない場合（404 NOT_FOUND）。
	"""
	response.headers["Cache-Control"] = "no-store"
	return await user_service.get_profile(current_user, db)


@router.patch("/api/users/me", response_model=UserProfileResponse)
async def patch_my_profile(
	payload: UserProfileUpdateRequest,
	response: Response,
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> UserProfileResponse:
	"""PATCH /api/users/me: ログインユーザー自身のプロフィールを更新する。

	認可: 認証必須。sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。
	レスポンスは`Cache-Control: no-store`とする。

	Args:
		payload: 更新内容（`null`は許可しないフィールドを含む）。
		response: no-storeヘッダ設定先のResponse。
		current_user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで更新後のプロフィールを返す。

	Raises:
		NotFoundError: ユーザーが既に削除されている等で見つからない場合（404 NOT_FOUND）。
		ValidationError: `null`が許可されていないフィールドにnullが指定された場合（422 VALIDATION_ERROR）。
	"""
	response.headers["Cache-Control"] = "no-store"
	return await user_service.update_profile(current_user, payload, db)


@router.put("/api/users/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_password(
	payload: PasswordChangeRequest,
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> Response:
	"""PUT /api/users/me/password: ログインユーザー自身のパスワードを変更する。

	認可: 認証必須。sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		payload: 現在のパスワードと新しいパスワード。
		current_user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		204 No Contentを返す。

	Raises:
		NotFoundError: ユーザーが既に削除されている等で見つからない場合（404 NOT_FOUND）。
		InvalidCredentialsError: 現在のパスワードが一致しない場合（401 INVALID_CREDENTIALS）。
		ValidationError: `current_password`の要否（パスワード方式）を満たさない場合（422 VALIDATION_ERROR）。
	"""
	await user_service.change_password(current_user, payload, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/users/me/login-history", response_model=LoginHistoryListResponse)
async def get_my_login_history(
	response: Response,
	current_user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	settings: BackendSettings = Depends(get_backend_settings),
) -> LoginHistoryListResponse:
	"""GET /api/users/me/login-history: ログインユーザー自身の直近ログイン履歴を取得する。

	認可: 認証必須（未認証は401 UNAUTHENTICATED）。レスポンスは`Cache-Control: no-store`とする。

	Args:
		response: no-storeヘッダ設定先のResponse。
		current_user: 認証済みユーザー。
		db: DBセッション。
		settings: 取得件数上限（`login_history_list_limit`）を含む設定。

	Returns:
		200 OKでログイン履歴一覧を返す。
	"""
	response.headers["Cache-Control"] = "no-store"
	return await user_service.get_login_history(current_user, db, limit=settings.login_history_list_limit)

"""タスクコメントの参照・作成・更新・削除エンドポイント。

全エンドポイントはプロジェクトメンバーであることを前提とし、対象タスク・コメントが
存在しないか非公開な場合は404 NOT_FOUNDを返す。更新系はOrigin検証・CSRF検証を課す。
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
	get_comment_for_member,
	get_current_user,
	get_task_for_member,
	verify_csrf_if_session,
	verify_origin_if_session,
)
from app.db import get_db_session
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.schemas.auth import CurrentUser
from app.schemas.comment import CommentCreateRequest, CommentListResponse, CommentResponse, CommentUpdateRequest
from app.service import task_comment_service

router = APIRouter(tags=["comments"])


@router.get("/api/tasks/{task_id}/comments", response_model=CommentListResponse)
async def list_task_comments(
	task: Task = Depends(get_task_for_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> CommentListResponse:
	"""GET /api/tasks/{task_id}/comments: タスクに紐づくコメント一覧を取得する。

	認可: 認証必須。対象タスクへのアクセス権が無い場合は404 NOT_FOUND（`get_task_for_member`）。

	Args:
		task: パスの`task_id`から解決された対象タスク。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKでコメント一覧を返す。

	Raises:
		NotFoundError: タスクが存在しない場合（404 NOT_FOUND）。
	"""
	return await task_comment_service.list_comments(task, user, db)


@router.post(
	"/api/tasks/{task_id}/comments",
	response_model=CommentResponse,
	status_code=status.HTTP_201_CREATED,
)
async def create_task_comment(
	payload: CommentCreateRequest,
	task: Task = Depends(get_task_for_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> CommentResponse:
	"""POST /api/tasks/{task_id}/comments: タスクにコメントを追加する。

	認可: 認証必須。sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		payload: コメント本文。
		task: パスの`task_id`から解決された対象タスク。
		user: 認証済みユーザー（投稿者）。
		db: DBセッション。

	Returns:
		201 Createdで作成したコメントを返す。

	Raises:
		NotFoundError: タスクが存在しない場合（404 NOT_FOUND）。
	"""
	return await task_comment_service.add_comment(task, payload, user, db)


@router.patch("/api/comments/{comment_id}", response_model=CommentResponse)
async def update_task_comment(
	payload: CommentUpdateRequest,
	comment: TaskComment = Depends(get_comment_for_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> CommentResponse:
	"""PATCH /api/comments/{comment_id}: コメント本文を更新する。

	認可: 認証必須。コメント投稿者本人（または権限を満たすユーザー）のみ許可され、
	それ以外は403 FORBIDDENを返す（`require_comment_editor`）。
	sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		payload: 更新後のコメント本文。
		comment: パスの`comment_id`から解決された対象コメント。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		200 OKで更新後のコメントを返す。

	Raises:
		NotFoundError: コメントまたは紐づくタスクが存在しない場合（404 NOT_FOUND）。
		ForbiddenError: 投稿者以外が更新しようとした場合（403 FORBIDDEN）。
	"""
	return await task_comment_service.update_comment(comment.task, comment, payload, user, db)


@router.delete("/api/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_comment(
	comment: TaskComment = Depends(get_comment_for_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin_if_session),
	__csrf: None = Depends(verify_csrf_if_session),
) -> Response:
	"""DELETE /api/comments/{comment_id}: コメントを削除する。

	認可: 認証必須。コメント投稿者本人（または権限を満たすユーザー）のみ許可され、
	それ以外は403 FORBIDDENを返す（`require_comment_editor`）。
	sessionモードではOrigin検証・CSRF検証も課す（不正時403 CSRF_INVALID）。

	Args:
		comment: パスの`comment_id`から解決された対象コメント。
		user: 認証済みユーザー。
		db: DBセッション。

	Returns:
		204 No Contentを返す。

	Raises:
		NotFoundError: コメントまたは紐づくタスクが存在しない場合（404 NOT_FOUND）。
		ForbiddenError: 投稿者以外が削除しようとした場合（403 FORBIDDEN）。
	"""
	await task_comment_service.delete_comment(comment.task, comment, user, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
	get_comment_for_member,
	get_current_user,
	get_task_for_member,
	verify_csrf,
	verify_origin,
)
from app.db import get_db_session
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.schemas.auth import CurrentUser
from app.schemas.comment import CommentCreateRequest, CommentListResponse, CommentResponse
from app.service import task_comment_service

router = APIRouter(tags=["comments"])


@router.get("/api/tasks/{task_id}/comments", response_model=CommentListResponse)
async def list_task_comments(
	task: Task = Depends(get_task_for_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
) -> CommentListResponse:
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
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
) -> CommentResponse:
	return await task_comment_service.add_comment(task, payload, user, db)


@router.patch("/api/comments/{comment_id}", response_model=CommentResponse)
async def update_task_comment(
	payload: CommentCreateRequest,
	comment: TaskComment = Depends(get_comment_for_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
) -> CommentResponse:
	return await task_comment_service.update_comment(comment.task, comment, payload, user, db)


@router.delete("/api/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_comment(
	comment: TaskComment = Depends(get_comment_for_member),
	user: CurrentUser = Depends(get_current_user),
	db: AsyncSession = Depends(get_db_session),
	_: None = Depends(verify_origin),
	__csrf: None = Depends(verify_csrf),
) -> Response:
	await task_comment_service.delete_comment(comment.task, comment, user, db)
	return Response(status_code=status.HTTP_204_NO_CONTENT)

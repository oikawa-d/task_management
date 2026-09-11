from typing import Protocol, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.task import Task
from app.models.task_comment import TaskComment
from app.repository import task_comment_repository
from app.schemas.auth import CurrentUser
from app.schemas.comment import CommentAuthor, CommentCreateRequest, CommentListResponse, CommentResponse
from app.service.authorization_service import require_comment_editor, require_task_access


class _DisplayNameUser(Protocol):
	username: str


class _NamedDisplayNameUser(_DisplayNameUser, Protocol):
	last_name: str | None
	first_name: str | None


def _display_name(user: _DisplayNameUser) -> str:
	if hasattr(user, "last_name") and hasattr(user, "first_name"):
		named_user = cast(_NamedDisplayNameUser, user)
		return " ".join(part for part in (named_user.last_name, named_user.first_name) if part) or user.username
	return user.username


def _comment_response(comment: TaskComment, fallback_user: CurrentUser | None = None) -> CommentResponse:
	author = comment.author or fallback_user
	if author is None:
		raise NotFoundError()
	return CommentResponse(
		id=comment.id,
		task_id=comment.task_id,
		body=comment.body,
		author=CommentAuthor(id=author.id, username=author.username, display_name=_display_name(author)),
		created_at=comment.created_at,
		updated_at=comment.updated_at,
	)


async def list_comments(task: Task, user: CurrentUser, db: AsyncSession) -> CommentListResponse:
	await require_task_access(task, user, db)
	comments = await task_comment_repository.list_by_task(db, task.id)
	return CommentListResponse(
		task_id=task.id,
		items=[_comment_response(comment) for comment in comments],
		count=len(comments),
	)


async def add_comment(
	task: Task, payload: CommentCreateRequest, user: CurrentUser, db: AsyncSession
) -> CommentResponse:
	await require_task_access(task, user, db)
	comment_id = await task_comment_repository.create(db, task.id, user.id, payload.body)
	comment = await task_comment_repository.get_by_id(db, comment_id)
	if comment is None:
		raise NotFoundError()
	return _comment_response(comment, user)


async def update_comment(
	task: Task,
	comment: TaskComment,
	payload: CommentCreateRequest,
	user: CurrentUser,
	db: AsyncSession,
) -> CommentResponse:
	await require_task_access(task, user, db)
	require_comment_editor(comment.user_id, user)
	await task_comment_repository.update(db, comment.id, user.id, payload.body)
	updated = await task_comment_repository.get_by_id(db, comment.id)
	if updated is None:
		raise NotFoundError()
	return _comment_response(updated, user)


async def delete_comment(task: Task, comment: TaskComment, user: CurrentUser, db: AsyncSession) -> None:
	await require_task_access(task, user, db)
	require_comment_editor(comment.user_id, user)
	await task_comment_repository.delete(db, comment.id, user.id)

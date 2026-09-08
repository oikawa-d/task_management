import uuid
from typing import Protocol

from app.core.exceptions import ForbiddenError, NotFoundError, UserInactiveError
from app.schemas.auth import CurrentUser

__all__ = [
	"CurrentUser",
	"assert_comment_editable",
	"authorize_project_member",
	"authorize_project_owner",
	"authorize_task_access",
]


class ProjectLike(Protocol):
	owner_id: uuid.UUID
	is_active: bool


class TaskLike(Protocol):
	project_id: uuid.UUID | None
	created_by: uuid.UUID
	is_active: bool


class CommentLike(Protocol):
	user_id: uuid.UUID


def _ensure_active_user(user: CurrentUser) -> None:
	if not user.is_active:
		raise UserInactiveError()


def authorize_project_member(user: CurrentUser, project: ProjectLike | None, is_member: bool) -> ProjectLike:
	_ensure_active_user(user)
	if project is None or not project.is_active or (user.role != "admin" and not is_member):
		raise NotFoundError()
	return project


def authorize_project_owner(user: CurrentUser, project: ProjectLike, is_member: bool) -> ProjectLike:
	authorize_project_member(user, project, is_member)
	if user.role != "admin" and project.owner_id != user.id:
		raise ForbiddenError()
	return project


def authorize_task_access(user: CurrentUser, task: TaskLike | None, is_member: bool) -> TaskLike:
	_ensure_active_user(user)
	if task is None or not task.is_active:
		raise NotFoundError()
	if user.role == "admin":
		return task
	if task.project_id is None:
		if task.created_by != user.id:
			raise NotFoundError()
		return task
	if not is_member:
		raise NotFoundError()
	return task


def assert_comment_editable(comment: CommentLike, user: CurrentUser) -> None:
	_ensure_active_user(user)
	if user.role != "admin" and comment.user_id != user.id:
		raise ForbiddenError()

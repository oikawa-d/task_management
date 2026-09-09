import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.task import Task
from app.repository import project_member_repository
from app.schemas.auth import CurrentUser


async def require_task_access(task: Task, user: CurrentUser, db: AsyncSession) -> None:
	if user.role == "admin":
		return
	if task.project_id is None:
		if task.created_by == user.id:
			return
		raise NotFoundError()
	if not await project_member_repository.exists(db, task.project_id, user.id):
		raise NotFoundError()


def require_comment_editor(comment_user_id: uuid.UUID, user: CurrentUser) -> None:
	if user.role != "admin" and comment_user_id != user.id:
		raise ForbiddenError()

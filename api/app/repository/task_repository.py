import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task


@dataclass(frozen=True)
class TaskWithProjectStatus:
	"""fn_get_task/fn_get_project_board/fn_list_tasks の1行分（タスク本体＋project_is_active）。"""

	task: Task
	project_is_active: bool | None


def _build_task(row: RowMapping) -> Task:
	return Task(
		id=row["id"],
		project_id=row["project_id"],
		title=row["title"],
		description=row["description"],
		status=row["status"],
		assignee_id=row["assignee_id"],
		created_by=row["created_by"],
		position=row["position"],
		version=row["version"],
		due_at=row["due_at"],
		is_active=row["is_active"],
		created_at=row["created_at"],
		updated_at=row["updated_at"],
	)


def _build_task_with_project_status(row: RowMapping) -> TaskWithProjectStatus:
	return TaskWithProjectStatus(task=_build_task(row), project_is_active=row["project_is_active"])


async def create(
	db: AsyncSession,
	project_id: uuid.UUID | None,
	created_by: uuid.UUID,
	assignee_id: uuid.UUID | None,
	title: str,
	body: str | None,
	status: str,
	due_at: datetime | None,
	position: int | None,
) -> uuid.UUID:
	result = await db.execute(
		text(
			"CALL sp_create_task(:project_id, :created_by, :assignee_id, :title, :body, "
			":status, :due_at, :position, NULL)"
		),
		{
			"project_id": project_id,
			"created_by": created_by,
			"assignee_id": assignee_id,
			"title": title,
			"body": body,
			"status": status,
			"due_at": due_at,
			"position": position,
		},
	)
	task_id: uuid.UUID = result.mappings().one()["p_task_id"]
	return task_id


async def get_by_id(db: AsyncSession, task_id: uuid.UUID) -> TaskWithProjectStatus | None:
	result = await db.execute(
		text("SELECT (task).*, project_is_active FROM fn_get_task(:task_id)"),
		{"task_id": task_id},
	)
	row = result.mappings().one_or_none()
	return None if row is None else _build_task_with_project_status(row)


async def list_board(db: AsyncSession, project_id: uuid.UUID, include_inactive: bool) -> list[TaskWithProjectStatus]:
	result = await db.execute(
		text("SELECT (task).*, project_is_active FROM fn_get_project_board(:project_id, :include_inactive)"),
		{"project_id": project_id, "include_inactive": include_inactive},
	)
	return [_build_task_with_project_status(row) for row in result.mappings().all()]


async def list_for_user(
	db: AsyncSession,
	user_id: uuid.UUID,
	project_id: uuid.UUID | None,
	status: str | None,
	include_inactive: bool,
	limit: int,
	offset: int,
) -> list[TaskWithProjectStatus]:
	result = await db.execute(
		text(
			"SELECT (task).*, project_is_active FROM "
			"fn_list_tasks(:user_id, :project_id, :status, :include_inactive, :limit, :offset)"
		),
		{
			"user_id": user_id,
			"project_id": project_id,
			"status": status,
			"include_inactive": include_inactive,
			"limit": limit,
			"offset": offset,
		},
	)
	return [_build_task_with_project_status(row) for row in result.mappings().all()]


async def update(
	db: AsyncSession,
	task_id: uuid.UUID,
	editor_id: uuid.UUID,
	version: int,
	title: str,
	body: str | None,
	status: str,
	assignee_id: uuid.UUID | None,
	due_at: datetime | None,
	position: int | None,
) -> None:
	await db.execute(
		text(
			"CALL sp_update_task(:task_id, :editor_id, :version, :title, :body, "
			":status, :assignee_id, :due_at, :position)"
		),
		{
			"task_id": task_id,
			"editor_id": editor_id,
			"version": version,
			"title": title,
			"body": body,
			"status": status,
			"assignee_id": assignee_id,
			"due_at": due_at,
			"position": position,
		},
	)


async def set_active(db: AsyncSession, task_id: uuid.UUID, is_active: bool) -> None:
	await db.execute(
		text("CALL sp_deactivate_task(:task_id, :is_active)"),
		{"task_id": task_id, "is_active": is_active},
	)

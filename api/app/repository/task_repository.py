import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task


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


async def get_by_id(db: AsyncSession, task_id: uuid.UUID) -> Task | None:
	result = await db.execute(
		select(Task)
		.from_statement(text("SELECT * FROM fn_get_task(:task_id)"))
		.params(task_id=task_id)
		.execution_options(populate_existing=True)
	)
	return result.scalars().one_or_none()


async def list_board(db: AsyncSession, project_id: uuid.UUID, include_inactive: bool) -> list[Task]:
	result = await db.execute(
		select(Task)
		.from_statement(text("SELECT * FROM fn_get_project_board(:project_id, :include_inactive)"))
		.params(project_id=project_id, include_inactive=include_inactive)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def list_for_user(
	db: AsyncSession,
	user_id: uuid.UUID,
	project_id: uuid.UUID | None,
	status: str | None,
	include_inactive: bool,
	limit: int,
	offset: int,
) -> list[Task]:
	result = await db.execute(
		select(Task)
		.from_statement(
			text("SELECT * FROM fn_list_tasks(:user_id, :project_id, :status, :include_inactive, :limit, :offset)")
		)
		.params(
			user_id=user_id,
			project_id=project_id,
			status=status,
			include_inactive=include_inactive,
			limit=limit,
			offset=offset,
		)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


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

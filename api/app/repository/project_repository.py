import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


@dataclass(frozen=True)
class ProjectListItem:
	"""fn_list_projects の1行分（プロジェクト本体＋集計値）。"""

	project: Project
	member_count: int
	task_count_todo: int
	task_count_in_progress: int
	task_count_done: int
	total_count: int


async def create(
	db: AsyncSession,
	owner_id: uuid.UUID,
	name: str,
	description: str | None,
	start_at: datetime | None,
	end_at: datetime | None,
) -> uuid.UUID:
	result = await db.execute(
		text("CALL sp_create_project(:owner_id, :name, :description, :start_at, :end_at, NULL)"),
		{
			"owner_id": owner_id,
			"name": name,
			"description": description,
			"start_at": start_at,
			"end_at": end_at,
		},
	)
	project_id: uuid.UUID = result.mappings().one()["p_project_id"]
	return project_id


async def get_by_id(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
	result = await db.execute(
		select(Project)
		.from_statement(text("SELECT * FROM fn_get_project(:project_id)"))
		.params(project_id=project_id)
		.execution_options(populate_existing=True)
	)
	return result.scalars().one_or_none()


async def list_for_user(
	db: AsyncSession, user_id: uuid.UUID, include_inactive: bool, limit: int, offset: int
) -> list[ProjectListItem]:
	result = await db.execute(
		text(
			"SELECT (project).*, member_count, task_count_todo, task_count_in_progress, "
			"task_count_done, total_count "
			"FROM fn_list_projects(:user_id, :include_inactive, :limit, :offset)"
		),
		{"user_id": user_id, "include_inactive": include_inactive, "limit": limit, "offset": offset},
	)
	rows = result.mappings().all()
	return [
		ProjectListItem(
			project=Project(
				id=row["id"],
				name=row["name"],
				description=row["description"],
				owner_id=row["owner_id"],
				is_active=row["is_active"],
				start_at=row["start_at"],
				end_at=row["end_at"],
				created_at=row["created_at"],
				updated_at=row["updated_at"],
			),
			member_count=row["member_count"],
			task_count_todo=row["task_count_todo"],
			task_count_in_progress=row["task_count_in_progress"],
			task_count_done=row["task_count_done"],
			total_count=row["total_count"],
		)
		for row in rows
	]


async def update(
	db: AsyncSession,
	project_id: uuid.UUID,
	name: str,
	description: str | None,
	start_at: datetime | None,
	end_at: datetime | None,
) -> None:
	await db.execute(
		text("CALL sp_update_project(:project_id, :name, :description, :start_at, :end_at)"),
		{
			"project_id": project_id,
			"name": name,
			"description": description,
			"start_at": start_at,
			"end_at": end_at,
		},
	)


async def set_active(db: AsyncSession, project_id: uuid.UUID, is_active: bool) -> None:
	await db.execute(
		text("CALL sp_deactivate_project(:project_id, :is_active)"),
		{"project_id": project_id, "is_active": is_active},
	)

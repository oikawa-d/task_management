import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_history import LoginHistory
from app.models.project import Project
from app.models.user import User


async def list_users(
	db: AsyncSession,
	query: str | None,
	role: str | None,
	is_active: bool | None,
	limit: int,
	offset: int,
) -> list[User]:
	result = await db.execute(
		select(User)
		.from_statement(text("SELECT * FROM fn_admin_list_users(:query, :role, :is_active, :limit, :offset)"))
		.params(query=query, role=role, is_active=is_active, limit=limit, offset=offset)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def list_projects(
	db: AsyncSession, query: str | None, is_active: bool | None, limit: int, offset: int
) -> list[Project]:
	result = await db.execute(
		select(Project)
		.from_statement(text("SELECT * FROM fn_admin_list_projects(:query, :is_active, :limit, :offset)"))
		.params(query=query, is_active=is_active, limit=limit, offset=offset)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def list_login_history(
	db: AsyncSession,
	user_id: uuid.UUID | None,
	query: str | None,
	login_method: str | None,
	success: bool | None,
	created_from: datetime | None,
	created_to: datetime | None,
	limit: int,
	offset: int,
) -> list[LoginHistory]:
	result = await db.execute(
		select(LoginHistory)
		.from_statement(
			text(
				"SELECT * FROM fn_admin_list_login_history("
				":user_id, :query, :login_method, :success, :created_from, :created_to, :limit, :offset)"
			)
		)
		.params(
			user_id=user_id,
			query=query,
			login_method=login_method,
			success=success,
			created_from=created_from,
			created_to=created_to,
			limit=limit,
			offset=offset,
		)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def update_user_role(db: AsyncSession, actor_id: uuid.UUID, target_id: uuid.UUID, new_role: str) -> None:
	await db.execute(
		text("CALL sp_admin_update_user_role(:actor_id, :target_id, :new_role)"),
		{"actor_id": actor_id, "target_id": target_id, "new_role": new_role},
	)


async def update_user_status(db: AsyncSession, actor_id: uuid.UUID, target_id: uuid.UUID, is_active: bool) -> None:
	await db.execute(
		text("CALL sp_admin_update_user_status(:actor_id, :target_id, :is_active)"),
		{"actor_id": actor_id, "target_id": target_id, "is_active": is_active},
	)


async def deactivate_project(db: AsyncSession, project_id: uuid.UUID, is_active: bool) -> None:
	await db.execute(
		text("CALL sp_admin_deactivate_project(:project_id, :is_active)"),
		{"project_id": project_id, "is_active": is_active},
	)

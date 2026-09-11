import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyMemberError
from app.models.project_member import ProjectMember
from app.models.user import User


async def create(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, invited_by: uuid.UUID | None) -> None:
	try:
		await db.execute(
			text("CALL sp_add_project_member(:project_id, :user_id, :invited_by)"),
			{"project_id": project_id, "user_id": user_id, "invited_by": invited_by},
		)
	except DBAPIError as exc:
		if getattr(exc.orig, "sqlstate", None) == "P0003":
			raise AlreadyMemberError() from exc
		raise


async def exists(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
	result = await db.execute(
		text("SELECT fn_is_project_member(:project_id, :user_id) AS is_member"),
		{"project_id": project_id, "user_id": user_id},
	)
	return bool(result.scalar_one())


async def list_by_project(db: AsyncSession, project_id: uuid.UUID) -> list[ProjectMember]:
	result = await db.execute(
		select(ProjectMember)
		.from_statement(text("SELECT * FROM fn_list_project_members(:project_id)"))
		.params(project_id=project_id)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def search_candidates(
	db: AsyncSession, project_id: uuid.UUID, query: str | None, limit: int, offset: int
) -> list[User]:
	result = await db.execute(
		select(User)
		.from_statement(text("SELECT * FROM fn_search_member_candidates(:project_id, :query, :limit, :offset)"))
		.params(project_id=project_id, query=query, limit=limit, offset=offset)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def delete(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
	await db.execute(
		text("CALL sp_remove_project_member(:project_id, :user_id)"),
		{"project_id": project_id, "user_id": user_id},
	)

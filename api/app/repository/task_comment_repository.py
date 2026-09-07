import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_comment import TaskComment


async def create(db: AsyncSession, task_id: uuid.UUID, user_id: uuid.UUID, body: str) -> uuid.UUID:
	result = await db.execute(
		text("CALL sp_add_task_comment(:task_id, :user_id, :body, NULL)"),
		{"task_id": task_id, "user_id": user_id, "body": body},
	)
	comment_id: uuid.UUID = result.mappings().one()["p_comment_id"]
	return comment_id


async def list_by_task(db: AsyncSession, task_id: uuid.UUID) -> list[TaskComment]:
	result = await db.execute(
		select(TaskComment)
		.from_statement(text("SELECT * FROM fn_list_task_comments(:task_id)"))
		.params(task_id=task_id)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def get_by_id(db: AsyncSession, comment_id: uuid.UUID) -> TaskComment | None:
	result = await db.execute(
		select(TaskComment)
		.from_statement(text("SELECT * FROM fn_get_comment_with_task(:comment_id)"))
		.params(comment_id=comment_id)
		.execution_options(populate_existing=True)
	)
	return result.scalars().one_or_none()


async def update(db: AsyncSession, comment_id: uuid.UUID, user_id: uuid.UUID, body: str) -> None:
	await db.execute(
		text("CALL sp_update_task_comment(:comment_id, :user_id, :body)"),
		{"comment_id": comment_id, "user_id": user_id, "body": body},
	)


async def delete(db: AsyncSession, comment_id: uuid.UUID, user_id: uuid.UUID) -> None:
	await db.execute(
		text("CALL sp_delete_task_comment(:comment_id, :user_id)"),
		{"comment_id": comment_id, "user_id": user_id},
	)

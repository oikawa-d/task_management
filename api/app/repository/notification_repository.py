import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def list_by_user(
	db: AsyncSession, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
) -> list[Notification]:
	result = await db.execute(
		select(Notification)
		.from_statement(text("SELECT * FROM fn_list_notifications(:user_id, :unread_only, :limit, :offset)"))
		.params(user_id=user_id, unread_only=unread_only, limit=limit, offset=offset)
		.execution_options(populate_existing=True)
	)
	return list(result.scalars().all())


async def count_unread(db: AsyncSession, user_id: uuid.UUID) -> int:
	result = await db.execute(
		text("SELECT fn_count_unread_notifications(:user_id) AS count"),
		{"user_id": user_id},
	)
	return int(result.scalar_one())


async def mark_read(db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
	await db.execute(
		text("CALL sp_mark_notification_read(:notification_id, :user_id)"),
		{"notification_id": notification_id, "user_id": user_id},
	)


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> None:
	await db.execute(text("CALL sp_mark_all_notifications_read(:user_id)"), {"user_id": user_id})


async def purge_expired(db: AsyncSession, retention_days: int) -> None:
	await db.execute(text("CALL sp_purge_notifications(:retention_days)"), {"retention_days": retention_days})

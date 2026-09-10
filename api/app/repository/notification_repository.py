import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


@dataclass(frozen=True)
class NotificationListItem:
	"""fn_list_notifications の1行分（通知本体＋task情報＋全体件数）。"""

	notification: Notification
	task_title: str | None
	task_project_id: uuid.UUID | None
	total_count: int


def validate_page_window(limit: int, offset: int) -> None:
	if limit < 1:
		raise ValueError("limit must be positive")
	if offset < 0:
		raise ValueError("offset must not be negative")


async def list_by_user(
	db: AsyncSession, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
) -> list[NotificationListItem]:
	validate_page_window(limit, offset)
	result = await db.execute(
		text(
			"SELECT (notification).*, task_title, task_project_id, total_count "
			"FROM fn_list_notifications(:user_id, :unread_only, :limit, :offset)"
		),
		{"user_id": user_id, "unread_only": unread_only, "limit": limit, "offset": offset},
	)
	rows = result.mappings().all()
	return [
		NotificationListItem(
			notification=Notification(
				id=row["id"],
				user_id=row["user_id"],
				task_id=row["task_id"],
				type=row["type"],
				title=row["title"],
				body=row["body"],
				due_at=row["due_at"],
				dedupe_key=row["dedupe_key"],
				read_at=row["read_at"],
				created_at=row["created_at"],
			),
			task_title=row["task_title"],
			task_project_id=row["task_project_id"],
			total_count=row["total_count"],
		)
		for row in rows
	]


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

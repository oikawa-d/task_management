import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository import notification_repository

NOTIFICATION_TYPE = "due_soon_batch"
NOTIFICATION_BODY = "期限が近いタスクです"


@dataclass(frozen=True)
class DueTask:
	id: uuid.UUID
	title: str
	assignee_id: uuid.UUID
	due_at: datetime


async def bulk_create_due_notifications(
	db: AsyncSession,
	tasks: Sequence[DueTask],
	run_date: date,
	notification_slot: str,
	chunk_size: int,
) -> int:
	if chunk_size <= 0:
		raise ValueError("chunk_size must be positive")

	created_count = 0
	for start in range(0, len(tasks), chunk_size):
		chunk = tasks[start : start + chunk_size]
		payloads = [_to_notification_payload(task, run_date, notification_slot) for task in chunk]
		try:
			created_count += await notification_repository.bulk_create_if_absent(db, payloads)
			await db.commit()
		except Exception:
			await db.rollback()
			raise
	return created_count


def _to_notification_payload(task: DueTask, run_date: date, notification_slot: str) -> dict[str, object]:
	return {
		"user_id": task.assignee_id,
		"task_id": task.id,
		"type": NOTIFICATION_TYPE,
		"title": task.title,
		"body": NOTIFICATION_BODY,
		"due_at": task.due_at,
		"dedupe_key": f"batch:{run_date.isoformat()}:{notification_slot}:{task.id}",
	}

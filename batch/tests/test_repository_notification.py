import uuid
from datetime import datetime, timezone

from app.repository import notification_repository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_bulk_create_if_absent_ignores_same_user_and_dedupe_key_duplicate(
	db_session: AsyncSession,
) -> None:
	user_id = await _create_user(db_session, "batch-notification@example.com")
	task_id = await _create_task(db_session, user_id)
	payload = {
		"user_id": user_id,
		"task_id": task_id,
		"type": "due_soon_batch",
		"title": "期限タスク",
		"body": "期限が近いタスクです",
		"due_at": datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
		"dedupe_key": f"batch:2026-09-07:10:{task_id}",
	}

	assert await notification_repository.bulk_create_if_absent(db_session, [payload]) == 1
	assert await notification_repository.bulk_create_if_absent(db_session, [payload]) == 0

	count = await db_session.scalar(
		text("SELECT count(*) FROM notifications WHERE user_id = :user_id"),
		{"user_id": user_id},
	)
	assert count == 1


async def _create_user(db_session: AsyncSession, email: str) -> uuid.UUID:
	return (
		await db_session.execute(
			text(
				"INSERT INTO users (username, email, password_hash) "
				"VALUES (:username, :email, :password_hash) RETURNING id"
			),
			{"username": email.split("@")[0], "email": email, "password_hash": "hash"},
		)
	).scalar_one()


async def _create_task(db_session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
	return (
		await db_session.execute(
			text(
				"INSERT INTO tasks (title, created_by, assignee_id, due_at) "
				"VALUES ('期限タスク', :user_id, :user_id, now()) RETURNING id"
			),
			{"user_id": user_id},
		)
	).scalar_one()

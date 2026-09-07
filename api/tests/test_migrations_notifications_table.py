import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_user(db: AsyncSession, username: str) -> str:
	row = (
		await db.execute(
			text("INSERT INTO users (username, email, password_hash) VALUES (:username, :email, 'hash') RETURNING id"),
			{"username": username, "email": f"{username}@example.com"},
		)
	).scalar_one()
	return str(row)


async def test_notification_check_constraint_rejects_invalid_type(db_session: AsyncSession) -> None:
	user_id = await _create_user(db_session, "notif1")

	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO notifications (user_id, type, title, dedupe_key) VALUES (:user_id, 'invalid', 't', 'k1')"
			),
			{"user_id": user_id},
		)


async def test_create_if_absent_ignores_duplicate_dedupe_key(db_session: AsyncSession) -> None:
	user_id = await _create_user(db_session, "notif2")

	first = (
		await db_session.execute(
			text(
				"INSERT INTO notifications (user_id, type, title, dedupe_key) "
				"VALUES (:user_id, 'due_today_created', 't', 'k2') "
				"ON CONFLICT (user_id, dedupe_key) DO NOTHING RETURNING id"
			),
			{"user_id": user_id},
		)
	).fetchall()
	await db_session.commit()

	second = (
		await db_session.execute(
			text(
				"INSERT INTO notifications (user_id, type, title, dedupe_key) "
				"VALUES (:user_id, 'due_today_created', 't2', 'k2') "
				"ON CONFLICT (user_id, dedupe_key) DO NOTHING RETURNING id"
			),
			{"user_id": user_id},
		)
	).fetchall()

	assert len(first) == 1
	assert len(second) == 0


async def test_delete_user_cascades_notifications(db_session: AsyncSession) -> None:
	user_id = await _create_user(db_session, "notif3")
	notification_id = (
		await db_session.execute(
			text(
				"INSERT INTO notifications (user_id, type, title, dedupe_key) "
				"VALUES (:user_id, 'due_today_created', 't', 'k3') RETURNING id"
			),
			{"user_id": user_id},
		)
	).scalar_one()

	await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

	count = (
		await db_session.execute(text("SELECT count(*) FROM notifications WHERE id = :id"), {"id": notification_id})
	).scalar_one()
	assert count == 0


async def test_delete_task_sets_notification_task_id_null(db_session: AsyncSession) -> None:
	user_id = await _create_user(db_session, "notif4")
	task_id = (
		await db_session.execute(
			text("INSERT INTO tasks (created_by, title) VALUES (:uid, 't') RETURNING id"),
			{"uid": user_id},
		)
	).scalar_one()
	notification_id = (
		await db_session.execute(
			text(
				"INSERT INTO notifications (user_id, task_id, type, title, dedupe_key) "
				"VALUES (:user_id, :task_id, 'due_today_created', 't', 'k4') RETURNING id"
			),
			{"user_id": user_id, "task_id": task_id},
		)
	).scalar_one()

	await db_session.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})

	remaining_task_id = (
		await db_session.execute(text("SELECT task_id FROM notifications WHERE id = :id"), {"id": notification_id})
	).scalar_one()
	assert remaining_task_id is None


async def test_uq_notifications_user_dedupe_rejects_duplicate_without_on_conflict(db_session: AsyncSession) -> None:
	user_id = await _create_user(db_session, "notif5")
	await db_session.execute(
		text(
			"INSERT INTO notifications (user_id, type, title, dedupe_key) "
			"VALUES (:user_id, 'due_today_created', 't', 'k5')"
		),
		{"user_id": user_id},
	)

	with pytest.raises(IntegrityError):
		await db_session.execute(
			text(
				"INSERT INTO notifications (user_id, type, title, dedupe_key) "
				"VALUES (:user_id, 'due_today_created', 't2', 'k5')"
			),
			{"user_id": user_id},
		)

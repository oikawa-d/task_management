import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def test_sp_purge_notifications_rejects_non_positive_days(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(text("CALL sp_purge_notifications(0)"))


async def test_sp_purge_api_history_rejects_non_positive_days(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(text("CALL sp_purge_api_history(-1)"))


async def test_sp_purge_batch_history_rejects_non_positive_days(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(text("CALL sp_purge_batch_history(0)"))


async def test_fn_list_due_notification_tasks_returns_only_active_assigned_due_before_threshold(
	db_session: AsyncSession,
) -> None:
	owner_id = (
		await db_session.execute(
			text(
				"INSERT INTO users (username, email, password_hash) "
				"VALUES ('duefn1', 'duefn1@example.com', 'h') RETURNING id"
			)
		)
	).scalar_one()

	# 対象：期限がthreshold以前・is_active=true・担当者あり
	due_task_id = (
		await db_session.execute(
			text(
				"INSERT INTO tasks (created_by, assignee_id, title, due_at) "
				"VALUES (:uid, :uid, 'due soon', now()) RETURNING id"
			),
			{"uid": owner_id},
		)
	).scalar_one()
	# 非対象：無効化タスク
	await db_session.execute(
		text(
			"INSERT INTO tasks (created_by, assignee_id, title, due_at, is_active) "
			"VALUES (:uid, :uid, 'inactive', now(), false)"
		),
		{"uid": owner_id},
	)
	# 非対象：担当者なし
	await db_session.execute(
		text("INSERT INTO tasks (created_by, title, due_at) VALUES (:uid, 'unassigned', now())"),
		{"uid": owner_id},
	)
	# 非対象：thresholdより後
	await db_session.execute(
		text(
			"INSERT INTO tasks (created_by, assignee_id, title, due_at) "
			"VALUES (:uid, :uid, 'future', now() + interval '1 day')"
		),
		{"uid": owner_id},
	)

	# thresholdはnow()+1分（境界の'due soon'のみ含み、'future'は除外する）
	result = await db_session.execute(
		text("SELECT id FROM fn_list_due_notification_tasks(now() + interval '1 minute')")
	)
	ids = {row[0] for row in result.fetchall()}

	assert ids == {due_task_id}


async def test_sp_purge_notifications_deletes_expired_regardless_of_read_state(db_session: AsyncSession) -> None:
	user_id = (
		await db_session.execute(
			text(
				"INSERT INTO users (username, email, password_hash) "
				"VALUES ('purgefn1', 'purgefn1@example.com', 'h') RETURNING id"
			)
		)
	).scalar_one()
	await db_session.execute(
		text(
			"INSERT INTO notifications (user_id, type, title, dedupe_key, created_at) "
			"VALUES (:user_id, 'due_today_created', 't', 'purge-old', now() - interval '100 days')"
		),
		{"user_id": user_id},
	)
	await db_session.execute(
		text(
			"INSERT INTO notifications (user_id, type, title, dedupe_key, created_at) "
			"VALUES (:user_id, 'due_today_created', 't', 'purge-recent', now())"
		),
		{"user_id": user_id},
	)

	await db_session.execute(text("CALL sp_purge_notifications(90)"))

	remaining = (
		(
			await db_session.execute(
				text("SELECT dedupe_key FROM notifications WHERE user_id = :user_id"), {"user_id": user_id}
			)
		)
		.scalars()
		.all()
	)
	assert remaining == ["purge-recent"]

"""通知・API履歴・バッチ履歴のパージ用ストアドプロシージャ、および
期限到来タスク抽出関数`fn_list_due_notification_tasks`の実DB結合テスト。
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def test_sp_purge_notifications_rejects_non_positive_days(db_session: AsyncSession) -> None:
	"""`sp_purge_notifications`に保持日数として0を渡した場合、
	`p_retention_days must be positive`例外により`DBAPIError`が送出されることを検証する。
	"""
	with pytest.raises(DBAPIError):
		await db_session.execute(text("CALL sp_purge_notifications(0)"))


async def test_sp_purge_api_history_rejects_non_positive_days(db_session: AsyncSession) -> None:
	"""`sp_purge_api_history`に保持日数として負数（-1）を渡した場合、
	同様に`DBAPIError`が送出されることを検証する。
	"""
	with pytest.raises(DBAPIError):
		await db_session.execute(text("CALL sp_purge_api_history(-1)"))


async def test_sp_purge_batch_history_rejects_non_positive_days(db_session: AsyncSession) -> None:
	"""`sp_purge_batch_history`に保持日数として0を渡した場合、
	同様に`DBAPIError`が送出されることを検証する。
	"""
	with pytest.raises(DBAPIError):
		await db_session.execute(text("CALL sp_purge_batch_history(0)"))


async def test_fn_list_due_notification_tasks_returns_only_active_assigned_due_before_threshold(
	db_session: AsyncSession,
) -> None:
	"""`fn_list_due_notification_tasks(threshold)`が、`is_active=true`かつ担当者ありかつ
	`status != 'done'`かつ`due_at < threshold`を全て満たすタスクのみを返し、
	無効化済み・担当者未設定・threshold超過・完了済みの各タスクは除外することを検証する。
	"""
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
	# 非対象：完了済み（status='done'）
	await db_session.execute(
		text(
			"INSERT INTO tasks (created_by, assignee_id, title, due_at, status) "
			"VALUES (:uid, :uid, 'done task', now(), 'done')"
		),
		{"uid": owner_id},
	)

	# thresholdはnow()+1分（境界の'due soon'のみ含み、'future'・'done task'は除外する）
	result = await db_session.execute(
		text("SELECT id FROM fn_list_due_notification_tasks(now() + interval '1 minute')")
	)
	ids = {row[0] for row in result.fetchall()}

	assert ids == {due_task_id}


async def test_sp_purge_notifications_deletes_expired_regardless_of_read_state(db_session: AsyncSession) -> None:
	"""`sp_purge_notifications(90)`実行後、`created_at`が90日を超えて経過した通知は
	既読・未読の状態にかかわらず削除され、保持期間内の通知のみが残ることを検証する。
	"""
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

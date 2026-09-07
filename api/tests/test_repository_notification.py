import uuid

from app.repository import notification_repository, user_repository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_notification(db: AsyncSession, user_id, dedupe_key: str, read_at_expr: str = "NULL") -> str:
	"""read_at_exprは'NULL'または'now()'系のSQL式リテラルを直接埋め込む（テスト専用ヘルパーのため許容）。"""
	row = (
		await db.execute(
			text(
				"INSERT INTO notifications (user_id, type, title, dedupe_key, read_at) "
				f"VALUES (:user_id, 'due_today_created', 't', :dedupe_key, {read_at_expr}) RETURNING id"
			),
			{"user_id": user_id, "dedupe_key": dedupe_key},
		)
	).scalar_one()
	return str(row)


async def test_list_by_user_returns_created_at_desc(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "notiflist1", "notiflist1@example.com", "hash")
	await db_session.execute(
		text(
			"INSERT INTO notifications (user_id, type, title, dedupe_key, created_at) "
			"VALUES (:user_id, 'due_today_created', 'old', 'k1', now() - interval '1 hour')"
		),
		{"user_id": user_id},
	)
	await db_session.execute(
		text(
			"INSERT INTO notifications (user_id, type, title, dedupe_key, created_at) "
			"VALUES (:user_id, 'due_today_created', 'new', 'k2', now())"
		),
		{"user_id": user_id},
	)

	notifications = await notification_repository.list_by_user(
		db_session, user_id, unread_only=False, limit=10, offset=0
	)

	assert [n.title for n in notifications] == ["new", "old"]


async def test_list_by_user_handles_deleted_task_gracefully(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "notiflist2", "notiflist2@example.com", "hash")
	task_id = (
		await db_session.execute(
			text("INSERT INTO tasks (created_by, title) VALUES (:uid, 't') RETURNING id"), {"uid": user_id}
		)
	).scalar_one()
	await db_session.execute(
		text(
			"INSERT INTO notifications (user_id, task_id, type, title, dedupe_key) "
			"VALUES (:user_id, :task_id, 'due_today_created', 't', 'k3')"
		),
		{"user_id": user_id, "task_id": task_id},
	)
	await db_session.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})

	notifications = await notification_repository.list_by_user(
		db_session, user_id, unread_only=False, limit=10, offset=0
	)

	assert len(notifications) == 1
	assert notifications[0].task_id is None


async def test_list_by_user_unread_only_excludes_read(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "notiflist3", "notiflist3@example.com", "hash")
	await _create_notification(db_session, user_id, "k4", read_at_expr="now()")
	await _create_notification(db_session, user_id, "k5")

	notifications = await notification_repository.list_by_user(
		db_session, user_id, unread_only=True, limit=10, offset=0
	)

	assert len(notifications) == 1
	assert notifications[0].dedupe_key == "k5"


async def test_count_unread_returns_unread_only(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "notifcount1", "notifcount1@example.com", "hash")
	for i in range(3):
		await _create_notification(db_session, user_id, f"unread-{i}")
	for i in range(2):
		await _create_notification(db_session, user_id, f"read-{i}", read_at_expr="now()")

	count = await notification_repository.count_unread(db_session, user_id)

	assert count == 3


async def test_mark_read_is_idempotent(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "notifread1", "notifread1@example.com", "hash")
	notification_id = await _create_notification(db_session, user_id, "k6")

	await notification_repository.mark_read(db_session, notification_id, user_id)
	first_read_at = (
		await db_session.execute(text("SELECT read_at FROM notifications WHERE id = :id"), {"id": notification_id})
	).scalar_one()

	await notification_repository.mark_read(db_session, notification_id, user_id)
	second_read_at = (
		await db_session.execute(text("SELECT read_at FROM notifications WHERE id = :id"), {"id": notification_id})
	).scalar_one()

	assert first_read_at is not None
	assert first_read_at == second_read_at


async def test_mark_read_other_users_notification_does_not_update(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "notifread2", "notifread2@example.com", "hash")
	other_id = await user_repository.create(db_session, "notifread3", "notifread3@example.com", "hash")
	notification_id = await _create_notification(db_session, owner_id, "k7")

	await notification_repository.mark_read(db_session, notification_id, other_id)

	read_at = (
		await db_session.execute(text("SELECT read_at FROM notifications WHERE id = :id"), {"id": notification_id})
	).scalar_one()
	assert read_at is None


async def test_mark_all_read_only_updates_unread_rows(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "notifreadall1", "notifreadall1@example.com", "hash")
	already_read_id = await _create_notification(db_session, user_id, "k8", read_at_expr="now() - interval '1 day'")
	unread_id = await _create_notification(db_session, user_id, "k9")

	before_read_at = (
		await db_session.execute(text("SELECT read_at FROM notifications WHERE id = :id"), {"id": already_read_id})
	).scalar_one()

	await notification_repository.mark_all_read(db_session, user_id)

	after_already_read_at = (
		await db_session.execute(text("SELECT read_at FROM notifications WHERE id = :id"), {"id": already_read_id})
	).scalar_one()
	newly_read_at = (
		await db_session.execute(text("SELECT read_at FROM notifications WHERE id = :id"), {"id": unread_id})
	).scalar_one()

	assert after_already_read_at == before_read_at
	assert newly_read_at is not None


async def test_purge_expired_deletes_regardless_of_read_state(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "notifpurge1", "notifpurge1@example.com", "hash")
	await db_session.execute(
		text(
			"INSERT INTO notifications (user_id, type, title, dedupe_key, read_at, created_at) "
			"VALUES (:user_id, 'due_today_created', 't', 'old-unread', NULL, now() - interval '100 days')"
		),
		{"user_id": user_id},
	)
	await db_session.execute(
		text(
			"INSERT INTO notifications (user_id, type, title, dedupe_key, read_at, created_at) "
			"VALUES (:user_id, 'due_today_created', 't', 'old-read', now(), now() - interval '100 days')"
		),
		{"user_id": user_id},
	)
	recent_id = await _create_notification(db_session, user_id, "recent")

	await notification_repository.purge_expired(db_session, retention_days=90)

	remaining = await notification_repository.list_by_user(db_session, user_id, unread_only=False, limit=10, offset=0)
	assert [n.id for n in remaining] == [uuid.UUID(recent_id)]

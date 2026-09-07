from app.repository import purge_repository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_purge_notifications_deletes_expired_read_and_unread_rows(
	db_session: AsyncSession,
) -> None:
	user_id = (
		await db_session.execute(
			text(
				"INSERT INTO users (username, email, password_hash) "
				"VALUES ('batch-purge', 'batch-purge@example.com', 'hash') RETURNING id"
			)
		)
	).scalar_one()
	await db_session.execute(
		text(
			"INSERT INTO notifications "
			"(user_id, type, title, dedupe_key, read_at, created_at) VALUES "
			"(:user_id, 'due_today_created', 'old unread', 'purge-old-unread', NULL, now() - interval '100 days'), "
			"(:user_id, 'due_today_created', 'old read', 'purge-old-read', now(), now() - interval '100 days'), "
			"(:user_id, 'due_today_created', 'recent', 'purge-recent', NULL, now())"
		),
		{"user_id": user_id},
	)

	await purge_repository.purge_notifications(db_session, retention_days=90)

	remaining = (
		(
			await db_session.execute(
				text("SELECT dedupe_key FROM notifications WHERE user_id = :user_id ORDER BY dedupe_key"),
				{"user_id": user_id},
			)
		)
		.scalars()
		.all()
	)
	assert remaining == ["purge-recent"]

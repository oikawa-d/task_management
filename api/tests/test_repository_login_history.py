from app.repository import login_history_repository, user_repository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_create_records_successful_login(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "alice", "alice@example.com", "hash")

	await login_history_repository.create(
		db_session,
		user_id=user_id,
		login_identifier="alice",
		login_method="session",
		ip_address="127.0.0.1",
		user_agent="pytest",
		success=True,
		failure_reason=None,
	)

	histories = await login_history_repository.list_by_user_id(db_session, user_id)
	assert len(histories) == 1
	assert histories[0].success is True
	assert histories[0].failure_reason is None


async def test_oauth_session_callback_records_user_email(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "alice", "alice@example.com", None)
	user = await user_repository.get_by_id(db_session, user_id)
	assert user is not None

	await login_history_repository.create(
		db_session,
		user_id=user_id,
		login_identifier=user.email,
		login_method="oauth_google",
		ip_address="127.0.0.1",
		user_agent="pytest",
		success=True,
		failure_reason=None,
	)

	histories = await login_history_repository.list_by_user_id(db_session, user_id)

	assert histories[0].login_identifier == user.email
	assert histories[0].login_method == "oauth_google"


async def test_oauth_jwt_exchange_records_user_email(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "bob", "bob@example.com", None)
	user = await user_repository.get_by_id(db_session, user_id)
	assert user is not None

	await login_history_repository.create(
		db_session,
		user_id=user_id,
		login_identifier=user.email,
		login_method="oauth_google",
		ip_address="127.0.0.1",
		user_agent="pytest",
		success=True,
		failure_reason=None,
	)

	histories = await login_history_repository.list_by_user_id(db_session, user_id)

	assert histories[0].login_identifier == user.email
	assert histories[0].login_method == "oauth_google"


async def test_create_records_failed_login_with_unregistered_identifier(db_session: AsyncSession) -> None:
	await login_history_repository.create(
		db_session,
		user_id=None,
		login_identifier="ghost",
		login_method="session",
		ip_address=None,
		user_agent=None,
		success=False,
		failure_reason="invalid_credentials",
	)

	row = (
		(
			await db_session.execute(
				text("SELECT user_id, success, failure_reason FROM login_history WHERE login_identifier = 'ghost'")
			)
		)
		.mappings()
		.one()
	)
	assert row["user_id"] is None
	assert row["success"] is False
	assert row["failure_reason"] == "invalid_credentials"


async def test_list_by_user_id_orders_by_created_at_desc(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "bob", "bob@example.com", "hash")
	for i in range(3):
		await db_session.execute(
			text(
				"INSERT INTO login_history (user_id, login_identifier, login_method, success, created_at) "
				"VALUES (:user_id, 'bob', 'session', true, now() - make_interval(mins => :offset))"
			),
			{"user_id": user_id, "offset": 3 - i},
		)

	histories = await login_history_repository.list_by_user_id(db_session, user_id, limit=2)

	assert len(histories) == 2
	assert histories[0].created_at > histories[1].created_at


async def test_purge_expired_deletes_only_old_rows(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "carol", "carol@example.com", "hash")
	await db_session.execute(
		text(
			"INSERT INTO login_history (user_id, login_identifier, login_method, success, created_at) "
			"VALUES (:user_id, 'carol', 'session', true, now() - interval '100 days')"
		),
		{"user_id": user_id},
	)
	await db_session.execute(
		text(
			"INSERT INTO login_history (user_id, login_identifier, login_method, success, created_at) "
			"VALUES (:user_id, 'carol', 'session', true, now() - interval '1 day')"
		),
		{"user_id": user_id},
	)

	await login_history_repository.purge_expired(db_session, retention_days=90)

	remaining = await login_history_repository.list_by_user_id(db_session, user_id)
	assert len(remaining) == 1

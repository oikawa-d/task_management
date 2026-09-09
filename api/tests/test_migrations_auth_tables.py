import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

_LOGIN_HISTORY_COMMENTS = {
	"id": "ログイン試行を一意に識別するUUID",
	"user_id": "未登録ID/メール入力時はNULL",
	"login_identifier": (
		"認証に使用した識別子。通常ログインはusername/email原文、Google OAuthは検証済みGoogle email。"
		"パスワード・OAuthのsub・トークンは記録しない"
	),
	"login_method": "ログイン方式。session / jwt / oauth_google",
	"ip_address": "信頼できるProxy情報から解決した接続元IPアドレス",
	"user_agent": "ログイン試行時のUser-Agent",
	"success": "ログイン試行の成否",
	"failure_reason": "ログイン失敗時の理由。成功時はNULL",
	"created_at": "ログイン試行を記録した日時",
}


async def test_users_table_created_with_default_role_and_active(db_session: AsyncSession) -> None:
	result = await db_session.execute(
		text(
			"INSERT INTO users (username, email, password_hash) "
			"VALUES ('alice', 'alice@example.com', 'hash') RETURNING role, is_active, email_verified_at"
		)
	)
	row = result.mappings().one()

	assert row["role"] == "member"
	assert row["is_active"] is True
	assert row["email_verified_at"] is None


async def test_users_username_uniqueness_is_case_insensitive(db_session: AsyncSession) -> None:
	await db_session.execute(
		text("INSERT INTO users (username, email, password_hash) VALUES ('Bob', 'b1@example.com', 'h')")
	)

	with pytest.raises(DBAPIError):
		await db_session.execute(
			text("INSERT INTO users (username, email, password_hash) VALUES ('bob', 'b2@example.com', 'h')")
		)


async def test_users_role_check_constraint_rejects_invalid_value(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO users (username, email, password_hash, role) "
				"VALUES ('carol', 'carol@example.com', 'h', 'superadmin')"
			)
		)


async def test_oauth_accounts_cascade_delete_on_user_delete(db_session: AsyncSession) -> None:
	user_id = (
		await db_session.execute(
			text(
				"INSERT INTO users (username, email, password_hash) "
				"VALUES ('dave', 'dave@example.com', 'h') RETURNING id"
			)
		)
	).scalar_one()
	await db_session.execute(
		text("INSERT INTO oauth_accounts (user_id, provider, provider_user_id) VALUES (:user_id, 'google', 'sub-1')"),
		{"user_id": user_id},
	)

	await db_session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})

	count = (
		await db_session.execute(
			text("SELECT count(*) FROM oauth_accounts WHERE user_id = :user_id"), {"user_id": user_id}
		)
	).scalar_one()
	assert count == 0


async def test_login_history_user_id_set_null_on_user_delete(db_session: AsyncSession) -> None:
	user_id = (
		await db_session.execute(
			text(
				"INSERT INTO users (username, email, password_hash) "
				"VALUES ('erin', 'erin@example.com', 'h') RETURNING id"
			)
		)
	).scalar_one()
	history_id = (
		await db_session.execute(
			text(
				"INSERT INTO login_history (user_id, login_identifier, login_method, success) "
				"VALUES (:user_id, 'erin', 'session', true) RETURNING id"
			),
			{"user_id": user_id},
		)
	).scalar_one()

	await db_session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})

	remaining_user_id = (
		await db_session.execute(text("SELECT user_id FROM login_history WHERE id = :id"), {"id": history_id})
	).scalar_one()
	assert remaining_user_id is None


async def test_users_updated_at_trigger_updates_timestamp(db_session: AsyncSession) -> None:
	created = (
		(
			await db_session.execute(
				text(
					"INSERT INTO users (username, email, password_hash) "
					"VALUES ('frank', 'frank@example.com', 'h') RETURNING id, updated_at"
				)
			)
		)
		.mappings()
		.one()
	)
	# now()はトランザクション開始時刻を返すため、INSERTとUPDATEを別トランザクションに分けて検証する
	await db_session.commit()

	updated = (
		(
			await db_session.execute(
				text("UPDATE users SET last_name = 'X' WHERE id = :id RETURNING updated_at"),
				{"id": created["id"]},
			)
		)
		.mappings()
		.one()
	)

	assert updated["updated_at"] > created["updated_at"]


async def test_login_history_failure_reason_consistency_check(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO login_history (login_identifier, login_method, success, failure_reason) "
				"VALUES ('ghost', 'session', true, 'invalid_credentials')"
			)
		)


async def test_login_history_column_comments_match_design(db_session: AsyncSession) -> None:
	table_comment = (
		await db_session.execute(text("SELECT obj_description('login_history'::regclass, 'pg_class')"))
	).scalar_one()
	result = await db_session.execute(
		text(
			"SELECT attname, col_description(attrelid, attnum) AS comment "
			"FROM pg_catalog.pg_attribute "
			"WHERE attrelid = 'login_history'::regclass "
			"AND attnum > 0 AND NOT attisdropped ORDER BY attnum"
		)
	)

	assert table_comment == "ログイン試行の監査ログ。Redis側のTTL失効とは独立して保持する"
	assert {row.attname: row.comment for row in result} == _LOGIN_HISTORY_COMMENTS

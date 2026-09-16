import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _insert_success(db: AsyncSession, request_id: uuid.UUID) -> None:
	await db.execute(
		text(
			"INSERT INTO api_history (request_id, method, path, status, status_code, duration_ms) "
			"VALUES (:request_id, 'GET', '/api/health', 'success', 200, 5)"
		),
		{"request_id": request_id},
	)


async def test_api_history_request_id_is_unique(db_session: AsyncSession) -> None:
	request_id = uuid.uuid4()
	await _insert_success(db_session, request_id)

	with pytest.raises(IntegrityError):
		await _insert_success(db_session, request_id)


async def test_api_history_status_check_rejects_invalid_value(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO api_history (request_id, method, path, status, status_code, duration_ms) "
				"VALUES (:request_id, 'GET', '/api/health', 'unknown', 200, 5)"
			),
			{"request_id": uuid.uuid4()},
		)


async def test_api_history_status_consistency_rejects_success_with_error_status_code(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO api_history (request_id, method, path, status, status_code, duration_ms) "
				"VALUES (:request_id, 'GET', '/api/health', 'success', 404, 5)"
			),
			{"request_id": uuid.uuid4()},
		)


async def test_api_history_error_row_requires_error_code_or_detail(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO api_history (request_id, method, path, status, status_code, duration_ms) "
				"VALUES (:request_id, 'GET', '/api/health', 'error', 500, 5)"
			),
			{"request_id": uuid.uuid4()},
		)


async def test_api_history_duration_ms_non_negative_check(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO api_history (request_id, method, path, status, status_code, duration_ms) "
				"VALUES (:request_id, 'GET', '/api/health', 'success', 200, -1)"
			),
			{"request_id": uuid.uuid4()},
		)


async def test_api_history_user_id_set_null_on_user_delete(db_session: AsyncSession) -> None:
	user_id = (
		await db_session.execute(
			text(
				"INSERT INTO users (username, email, password_hash) "
				"VALUES ('apihist1', 'apihist1@example.com', 'h') RETURNING id"
			)
		)
	).scalar_one()
	history_id = (
		await db_session.execute(
			text(
				"INSERT INTO api_history (request_id, method, path, status, status_code, duration_ms, user_id) "
				"VALUES (:request_id, 'GET', '/api/health', 'success', 200, 5, :user_id) RETURNING id"
			),
			{"request_id": uuid.uuid4(), "user_id": user_id},
		)
	).scalar_one()

	await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

	remaining_user_id = (
		await db_session.execute(text("SELECT user_id FROM api_history WHERE id = :id"), {"id": history_id})
	).scalar_one()
	assert remaining_user_id is None

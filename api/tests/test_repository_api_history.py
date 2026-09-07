import uuid
from datetime import datetime, timedelta, timezone

from app.repository import api_history_repository
from app.repository.api_history_repository import ApiHistoryCreateInput
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _input(request_id: uuid.UUID, **overrides: object) -> ApiHistoryCreateInput:
	defaults: dict[str, object] = {
		"request_id": request_id,
		"method": "GET",
		"path": "/api/notifications",
		"status": "success",
		"status_code": 200,
		"error_code": None,
		"error_detail": None,
		"body": None,
		"user_id": None,
		"ip_address": "127.0.0.1",
		"user_agent": "pytest",
		"duration_ms": 12,
	}
	defaults.update(overrides)
	return ApiHistoryCreateInput(**defaults)  # type: ignore[arg-type]


async def test_create_inserts_success_row(db_session: AsyncSession) -> None:
	request_id = uuid.uuid4()

	await api_history_repository.create(db_session, _input(request_id))

	history = await api_history_repository.list_by_request_id(db_session, request_id)
	assert history is not None
	assert history.status == "success"
	assert history.status_code == 200


async def test_create_inserts_error_row_with_body_json(db_session: AsyncSession) -> None:
	request_id = uuid.uuid4()

	await api_history_repository.create(
		db_session,
		_input(
			request_id,
			status="error",
			status_code=400,
			error_code="VALIDATION_ERROR",
			error_detail="invalid payload",
			body={"title": "***"},
		),
	)

	history = await api_history_repository.list_by_request_id(db_session, request_id)
	assert history is not None
	assert history.status == "error"
	assert history.error_code == "VALIDATION_ERROR"
	assert history.body == {"title": "***"}


async def test_create_uses_explicit_created_at_when_given(db_session: AsyncSession) -> None:
	request_id = uuid.uuid4()
	explicit_created_at = datetime.now(timezone.utc) - timedelta(days=1)

	await api_history_repository.create(db_session, _input(request_id, created_at=explicit_created_at))

	created_at = (
		await db_session.execute(
			text("SELECT created_at FROM api_history WHERE request_id = :request_id"), {"request_id": request_id}
		)
	).scalar_one()
	assert created_at == explicit_created_at


async def test_list_by_request_id_returns_none_when_not_found(db_session: AsyncSession) -> None:
	history = await api_history_repository.list_by_request_id(db_session, uuid.uuid4())
	assert history is None


async def test_purge_api_history_deletes_expired_rows(db_session: AsyncSession) -> None:
	old_request_id = uuid.uuid4()
	recent_request_id = uuid.uuid4()
	await db_session.execute(
		text(
			"INSERT INTO api_history (request_id, method, path, status, status_code, duration_ms, created_at) "
			"VALUES (:request_id, 'GET', '/api/health', 'success', 200, 5, now() - interval '40 days')"
		),
		{"request_id": old_request_id},
	)
	await db_session.execute(
		text(
			"INSERT INTO api_history (request_id, method, path, status, status_code, duration_ms) "
			"VALUES (:request_id, 'GET', '/api/health', 'success', 200, 5)"
		),
		{"request_id": recent_request_id},
	)

	await api_history_repository.purge_expired(db_session, retention_days=30)

	assert await api_history_repository.list_by_request_id(db_session, old_request_id) is None
	assert await api_history_repository.list_by_request_id(db_session, recent_request_id) is not None

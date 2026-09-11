import uuid
from unittest.mock import AsyncMock

import pytest
from app.core.exceptions import ServiceUnavailableError
from app.repository import login_history_repository
from sqlalchemy.exc import OperationalError


@pytest.mark.asyncio
async def test_create_calls_record_login_history_procedure() -> None:
	db = AsyncMock()
	user_id = uuid.uuid4()

	await login_history_repository.create(
		db,
		user_id=user_id,
		login_identifier="alice@example.com",
		login_method="session",
		ip_address="127.0.0.1",
		user_agent="pytest",
		success=False,
		failure_reason="invalid_credentials",
	)

	statement, params = db.execute.await_args.args
	assert "CALL sp_record_login_history" in str(statement)
	assert params == {
		"user_id": user_id,
		"login_identifier": "alice@example.com",
		"login_method": "session",
		"ip_address": "127.0.0.1",
		"user_agent": "pytest",
		"success": False,
		"failure_reason": "invalid_credentials",
	}


@pytest.mark.asyncio
async def test_create_translates_database_connection_error() -> None:
	db = AsyncMock()
	db.execute.side_effect = OperationalError("CALL", {}, ConnectionError("database unavailable"))

	with pytest.raises(ServiceUnavailableError):
		await login_history_repository.create(
			db,
			user_id=None,
			login_identifier="unknown",
			login_method="jwt",
			ip_address=None,
			user_agent=None,
			success=False,
			failure_reason="invalid_credentials",
		)


@pytest.mark.asyncio
async def test_all_login_history_db_operations_translate_operational_error() -> None:
	db = AsyncMock()
	db.execute.side_effect = OperationalError("statement", {}, ConnectionError("database unavailable"))

	operations = (
		login_history_repository.create(db, None, "unknown", "jwt", None, None, False, "invalid_credentials"),
		login_history_repository.list_by_user_id(db, uuid.uuid4()),
		login_history_repository.purge_expired(db, 90),
	)

	for operation in operations:
		with pytest.raises(ServiceUnavailableError):
			await operation

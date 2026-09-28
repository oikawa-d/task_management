"""app.repository.login_history_repository（ログイン履歴の記録・一覧取得・期限切れ削除）に対する単体テスト。
DB接続はAsyncMockで模擬し、実DBには接続しない。
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.exceptions import ServiceUnavailableError
from app.repository import login_history_repository
from sqlalchemy.exc import OperationalError


@pytest.mark.asyncio
async def test_create_calls_record_login_history_procedure() -> None:
	"""createが、指定した全パラメータ（user_id・login_identifier・login_method・ip_address・
	user_agent・success・failure_reason）を伴ってsp_record_login_historyストアドプロシージャを
	CALLしていることを検証する。
	"""
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
	"""DB接続エラー（sqlstate=08006）を表すOperationalErrorが発生した場合、
	createがそれをServiceUnavailableErrorへ変換して送出することを検証する。
	"""
	db = AsyncMock()
	db.execute.side_effect = OperationalError("CALL", {}, SimpleNamespace(sqlstate="08006"))

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
	"""create・list_by_user_id・purge_expiredのいずれも、DB接続エラー（sqlstate=08006）を表す
	OperationalErrorをServiceUnavailableErrorへ変換して送出することを検証する。
	"""
	db = AsyncMock()
	db.execute.side_effect = OperationalError("statement", {}, SimpleNamespace(sqlstate="08006"))

	operations = (
		login_history_repository.create(db, None, "unknown", "jwt", None, None, False, "invalid_credentials"),
		login_history_repository.list_by_user_id(db, uuid.uuid4()),
		login_history_repository.purge_expired(db, 90),
	)

	for operation in operations:
		with pytest.raises(ServiceUnavailableError):
			await operation

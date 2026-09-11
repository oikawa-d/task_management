import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from app.core.exceptions import ServiceUnavailableError
from app.models.user import User
from app.repository import user_repository
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError


class _ScalarResult:
	def __init__(self, value: User | None) -> None:
		self.value = value

	def scalars(self) -> "_ScalarResult":
		return self

	def one_or_none(self) -> User | None:
		return self.value


class _MappingResult:
	def __init__(self, user_id: uuid.UUID) -> None:
		self.user_id = user_id

	def mappings(self) -> "_MappingResult":
		return self

	def one(self) -> dict[str, uuid.UUID]:
		return {"p_user_id": self.user_id}


def _user(*, active: bool = True, verified: bool = True) -> User:
	return User(
		id=uuid.uuid4(),
		username="alice",
		email="alice@example.com",
		password_hash="hash",
		is_active=active,
		email_verified_at=None if not verified else datetime.now(),
	)


@pytest.mark.asyncio
async def test_get_by_login_identifier_keeps_inactive_unverified_user() -> None:
	db = AsyncMock()
	user = _user(active=False, verified=False)
	db.execute.return_value = _ScalarResult(user)

	actual = await user_repository.get_by_login_identifier(db, "alice")

	assert actual is user
	statement = db.execute.await_args.args[0]
	assert "fn_find_user_by_identifier" in str(statement)
	assert statement.compile().params == {"identifier": "alice"}


@pytest.mark.asyncio
async def test_get_by_id_returns_current_user_from_function() -> None:
	db = AsyncMock()
	user = _user()
	db.execute.return_value = _ScalarResult(user)

	actual = await user_repository.get_by_id(db, user.id)

	assert actual is user
	assert "fn_get_user" in str(db.execute.await_args.args[0])


@pytest.mark.asyncio
async def test_create_calls_register_procedure_and_returns_user_id() -> None:
	db = AsyncMock()
	user_id = uuid.uuid4()
	db.execute.return_value = _MappingResult(user_id)

	actual = await user_repository.create(db, "alice", "alice@example.com", "hash")

	assert actual == user_id
	statement, params = db.execute.await_args.args
	assert str(statement) == "CALL sp_register_user(:username, :email, :password_hash, NULL)"
	assert params == {"username": "alice", "email": "alice@example.com", "password_hash": "hash"}


@pytest.mark.asyncio
async def test_get_by_id_translates_database_connection_error() -> None:
	db = AsyncMock()
	db.execute.side_effect = OperationalError("SELECT", {}, ConnectionError("database unavailable"))

	with pytest.raises(ServiceUnavailableError):
		await user_repository.get_by_id(db, uuid.uuid4())


@pytest.mark.asyncio
async def test_all_user_db_operations_translate_operational_error() -> None:
	db = AsyncMock()
	db.execute.side_effect = OperationalError("statement", {}, ConnectionError("database unavailable"))
	user_id = uuid.uuid4()

	operations = (
		user_repository.get_by_id(db, user_id),
		user_repository.get_by_login_identifier(db, "alice"),
		user_repository.get_by_email(db, "alice@example.com"),
		user_repository.create(db, "alice", "alice@example.com", "hash"),
		user_repository.mark_email_verified(db, user_id),
		user_repository.update_password(db, user_id, "new-hash"),
		user_repository.update_profile(db, user_id, "山田", "太郎", "ヤマダ", "タロウ", None),
	)

	for operation in operations:
		with pytest.raises(ServiceUnavailableError):
			await operation


@pytest.mark.asyncio
async def test_create_keeps_integrity_error_contract() -> None:
	db = AsyncMock()
	exc = IntegrityError("CALL", {}, DBAPIError("duplicate", {}, Exception()))
	db.execute.side_effect = exc

	with pytest.raises(IntegrityError) as raised:
		await user_repository.create(db, "alice", "alice@example.com", "hash")

	assert raised.value is exc

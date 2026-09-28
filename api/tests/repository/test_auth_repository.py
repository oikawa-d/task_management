"""app.repository.user_repository（ユーザーの取得・作成・更新）に対する単体テスト。
DB接続はAsyncMockで模擬し、実DBには接続しない。認証で使うユーザー検索を扱うためこのファイルに配置されている。
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.exceptions import ServiceUnavailableError
from app.models.user import User
from app.repository import user_repository
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError


class _ScalarResult:
	"""SQLAlchemyのCursorResult風インターフェース（scalars().one_or_none()）を模擬するダミー結果セット。"""

	def __init__(self, value: User | None) -> None:
		"""返却するUser（またはNone）を保持する。"""
		self.value = value

	def scalars(self) -> "_ScalarResult":
		"""SQLAlchemyのResult.scalars()と同様、自身を返してメソッドチェーンを可能にする。"""
		return self

	def one_or_none(self) -> User | None:
		"""保持しているUser（またはNone）を返す。"""
		return self.value


class _MappingResult:
	"""ストアドプロシージャのOUTパラメータ（p_user_id）取得を模擬するダミー結果セット。"""

	def __init__(self, user_id: uuid.UUID) -> None:
		"""返却するユーザーIDを保持する。"""
		self.user_id = user_id

	def mappings(self) -> "_MappingResult":
		"""SQLAlchemyのResult.mappings()と同様、自身を返してメソッドチェーンを可能にする。"""
		return self

	def one(self) -> dict[str, uuid.UUID]:
		"""p_user_idキーに保持しているユーザーIDを持つ辞書を返す。"""
		return {"p_user_id": self.user_id}


def _user(*, active: bool = True, verified: bool = True) -> User:
	"""検証用のUserモデルインスタンスを作る。

	Args:
		active: is_activeに設定する値。
		verified: Trueならemail_verified_atに現在時刻を、Falseなら未検証(None)を設定する。

	Returns:
		指定した状態のUserインスタンス。
	"""
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
	"""get_by_login_identifierが、非アクティブ・未検証状態のユーザーであってもフィルタせずそのまま返し
	（有効性チェックは呼び出し側の責務）、fn_find_user_by_identifier関数を識別子で呼んでいることを検証する。
	"""
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
	"""get_by_idがユーザーIDに対応するUserを返し、fn_get_user関数を呼んでいることを検証する。"""
	db = AsyncMock()
	user = _user()
	db.execute.return_value = _ScalarResult(user)

	actual = await user_repository.get_by_id(db, user.id)

	assert actual is user
	assert "fn_get_user" in str(db.execute.await_args.args[0])


@pytest.mark.asyncio
async def test_create_calls_register_procedure_and_returns_user_id() -> None:
	"""createが、指定したusername・email・password_hashを引数にsp_register_userストアドプロシージャを
	CALLし、OUTパラメータとして返るユーザーIDを戻り値とすることを検証する。
	"""
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
	"""DB接続エラー（sqlstate=08006）を表すOperationalErrorが発生した場合、
	get_by_idがそれをServiceUnavailableErrorへ変換して送出することを検証する。
	"""
	db = AsyncMock()
	db.execute.side_effect = OperationalError("SELECT", {}, SimpleNamespace(sqlstate="08006"))

	with pytest.raises(ServiceUnavailableError):
		await user_repository.get_by_id(db, uuid.uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("sqlstate", "expected_error"),
	[("57P03", ServiceUnavailableError), ("40P01", OperationalError), (None, OperationalError)],
)
async def test_get_by_id_preserves_non_connection_operational_errors(
	sqlstate: str | None, expected_error: type[Exception]
) -> None:
	"""OperationalErrorのsqlstateが接続断（08006）ではない場合の変換方針を検証する。
	sqlstate=57P03（サーバー起動未完了）はServiceUnavailableErrorへ変換される一方、
	sqlstate=40P01（デッドロック）やsqlstate無しの場合はOperationalErrorのまま伝播することを確認する。
	"""
	db = AsyncMock()
	db.execute.side_effect = OperationalError("SELECT", {}, SimpleNamespace(sqlstate=sqlstate))

	with pytest.raises(expected_error):
		await user_repository.get_by_id(db, uuid.uuid4())


@pytest.mark.asyncio
async def test_all_user_db_operations_translate_operational_error() -> None:
	"""get_by_id・get_by_login_identifier・get_by_email・create・mark_email_verified・
	update_password・update_profileのいずれも、DB接続エラー（sqlstate=08006）を表す
	OperationalErrorをServiceUnavailableErrorへ変換して送出することを検証する。
	"""
	db = AsyncMock()
	db.execute.side_effect = OperationalError("statement", {}, SimpleNamespace(sqlstate="08006"))
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
	"""ユーザー作成時にメールアドレス重複等でIntegrityErrorが発生した場合、createはそれを
	ServiceUnavailableError等へ変換せず、呼び出し側が一意制約違反として扱えるよう
	元のIntegrityError（同一インスタンス）のまま伝播させることを検証する。
	"""
	db = AsyncMock()
	exc = IntegrityError("CALL", {}, DBAPIError("duplicate", {}, Exception()))
	db.execute.side_effect = exc

	with pytest.raises(IntegrityError) as raised:
		await user_repository.create(db, "alice", "alice@example.com", "hash")

	assert raised.value is exc

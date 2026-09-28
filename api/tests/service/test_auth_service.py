"""app.service.auth_service（ユーザー登録・ログイン・ログアウト・トークンリフレッシュ）の単体テスト。

DB・Redis・認証ストラテジー（session/JWT）・メール送信をすべてスタブ/モックに置き換え、
正常系に加えてSQLState変換や接続断・Redis障害時のフェイルクローズ挙動、
機微情報（パスワード・メールアドレス）がログへ漏えいしないことを検証する。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import (
	DuplicateEmailError,
	DuplicateUsernameError,
	EmailNotVerifiedError,
	InvalidCredentialsError,
	NotSupportedInModeError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	UserInactiveError,
)
from app.service import auth_service, email_verification_service
from sqlalchemy.exc import DBAPIError, DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


class _FakeRequest:
	"""FastAPIのRequestを模したスタブ。headers/client.host/stateのみをテストに必要な範囲で提供する。"""

	def __init__(self, headers: dict[str, str] | None = None) -> None:
		"""指定されたheadersと固定のクライアントIP・空のstateを持つリクエストスタブを初期化する。"""
		self.headers = headers or {}
		self.client = SimpleNamespace(host="203.0.113.10")
		self.state = SimpleNamespace()


class _FakeBackgroundTasks:
	"""FastAPIのBackgroundTasksを模したスタブ。add_task呼び出しの記録のみ行い、実際には実行しない。"""

	def __init__(self) -> None:
		"""登録されたタスクを記録するための空リストを用意する。"""
		self.tasks: list[tuple[object, tuple[object, ...]]] = []

	def add_task(self, func: object, *args: object) -> None:
		"""タスクを実行せず、呼び出された関数と引数の組をtasksへ記録する。"""
		self.tasks.append((func, args))


class _FakeStrategy:
	"""session/JWTなど認証ストラテジーを模したスタブ。login/logout/rollback_loginの呼び出し履歴を記録する。"""

	def __init__(self, mode: str = "session") -> None:
		"""指定したauth_mode（既定はsession）と、各メソッドの呼び出し履歴を初期化する。"""
		self.mode = mode
		self.login_calls: list[object] = []
		self.logout_calls = 0
		self.rollback_calls: list[tuple[object, object]] = []

	async def login(self, user: object, _request: object, _response: object) -> str:
		"""ログイン処理を模し、呼び出されたuserを記録して固定の成功結果文字列を返す。"""
		self.login_calls.append(user)
		return "login-result"

	async def logout(self, _request: object, _response: object) -> None:
		"""ログアウト処理を模し、呼び出し回数のみをカウントする。"""
		self.logout_calls += 1

	async def rollback_login(self, user: object, result: object, _response: object) -> None:
		"""ログイン後処理（login_history書き込み等）失敗時のロールバック呼び出しを記録する。"""
		self.rollback_calls.append((user, result))


class _RegisterDb:
	"""DBセッションを模したスタブ。commit/rollback呼び出し順序を記録し、任意でcommit時に例外を送出できる。"""

	def __init__(self, commit_error: Exception | None = None) -> None:
		"""呼び出し履歴を空で初期化し、commit_errorが指定された場合はcommit時にその例外を送出するよう設定する。"""
		self.calls: list[str] = []
		self.commit_error = commit_error

	async def commit(self) -> None:
		"""commit呼び出しを記録し、commit_errorが設定されていればそれを送出する。"""
		self.calls.append("db.commit")
		if self.commit_error is not None:
			raise self.commit_error

	async def rollback(self) -> None:
		"""rollback呼び出しを記録する。"""
		self.calls.append("db.rollback")


def _register_payload(**overrides: object) -> auth_service.RegisterRequest:
	"""register用のRegisterRequestを既定値から生成する。overridesで一部フィールドを上書きできる。"""
	values: dict[str, object] = {
		"username": "taro",
		"email": "taro@example.com",
		"password": "Passw0rd!",
		"password_confirm": "Passw0rd!",
		"last_name": "山田",
		"first_name": "太郎",
		"last_name_kana": "ヤマダ",
		"first_name_kana": "タロウ",
		"birth_date": "1995-04-01",
	}
	values.update(overrides)
	return auth_service.RegisterRequest(**values)  # type: ignore[arg-type]


def _login_user(*, is_active: bool = True, verified: bool = True, password_hash: str | None = "hash"):
	"""login用のユーザースタブ（SimpleNamespace）を生成する。is_active/verified/password_hashで各状態を切り替えられる。"""
	return SimpleNamespace(
		id=uuid4(),
		username="taro",
		email="taro@example.com",
		password_hash=password_hash,
		is_active=is_active,
		email_verified_at="2026-01-01T00:00:00+09:00" if verified else None,
	)


async def test_register_creates_user_and_schedules_verification(monkeypatch: pytest.MonkeyPatch) -> None:
	"""重複が無い正常系でregisterを呼ぶと、平文パスワードを保存せずユーザーを作成し、メール確認発行まで行われることを検証する。"""
	user_id = uuid4()
	created = SimpleNamespace(id=user_id, email="taro@example.com")
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	create_mock = AsyncMock(return_value=user_id)
	update_profile_mock = AsyncMock()
	monkeypatch.setattr(auth_service.user_repository, "create", create_mock)
	monkeypatch.setattr(auth_service.user_repository, "update_profile", update_profile_mock)
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=created))
	issue_mock = AsyncMock()
	monkeypatch.setattr(email_verification_service, "issue_email_verify_token", issue_mock)
	db = _RegisterDb()

	user = await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), db)  # type: ignore[arg-type]

	assert user is created
	assert db.calls == ["db.commit"]
	assert create_mock.await_args.args[1] == "taro"
	# 平文パスワードは保存しない（argon2idハッシュのみを渡す）。
	assert create_mock.await_args.args[3] != "Passw0rd!"
	update_profile_mock.assert_awaited_once()
	issue_mock.assert_awaited_once()


async def test_register_emits_user_registered_structured_log(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""登録完了時にevent=user_registeredが出力され、メール・パスワードが含まれないこと。"""
	user_id = uuid4()
	created = SimpleNamespace(id=user_id, email="taro@example.com")
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(return_value=user_id))
	monkeypatch.setattr(auth_service.user_repository, "update_profile", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=created))
	monkeypatch.setattr(email_verification_service, "issue_email_verify_token", AsyncMock())

	with caplog.at_level("INFO", logger="app.oauth"):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]

	user_registered_records = [r for r in caplog.records if getattr(r, "event", None) == "user_registered"]
	assert len(user_registered_records) == 1
	record = user_registered_records[0]
	assert record.user_id == str(user_id)
	assert "taro@example.com" not in caplog.text
	assert "Passw0rd!" not in caplog.text


async def test_register_duplicate_username_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""既存ユーザー名と重複する場合にDuplicateUsernameErrorを送出し、user_repository.createが呼ばれないことを検証する。"""
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=object()))
	create_mock = AsyncMock()
	monkeypatch.setattr(auth_service.user_repository, "create", create_mock)

	with pytest.raises(DuplicateUsernameError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]

	create_mock.assert_not_awaited()


async def test_register_duplicate_email_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""既存メールアドレスと重複する場合にDuplicateEmailErrorが送出されることを検証する。"""
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=object()))

	with pytest.raises(DuplicateEmailError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]


@pytest.mark.parametrize(
	("sqlstate", "expected"),
	[("P0001", DuplicateUsernameError), ("P0002", DuplicateEmailError)],
)
async def test_register_converts_sqlstate_to_conflict(
	monkeypatch: pytest.MonkeyPatch, sqlstate: str, expected: type[Exception]
) -> None:
	"""ストアドプロシージャがsqlstate P0001/P0002で失敗した場合、それぞれ重複ユーザー名/
	重複メールの例外へ変換されrollbackされることを検証する。
	"""
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	error = OperationalError("CALL sp_register_user", {}, SimpleNamespace(sqlstate=sqlstate))
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(side_effect=error))
	db = _RegisterDb()

	with pytest.raises(expected):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), db)  # type: ignore[arg-type]

	assert db.calls == ["db.rollback"]


async def test_register_reraises_unknown_sqlstate(monkeypatch: pytest.MonkeyPatch) -> None:
	"""未知のsqlstate（P0009）はアプリ固有の例外に変換されず、元のDBAPIErrorがそのまま再送出されrollbackされることを検証する。"""
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	error = DBAPIError("CALL sp_register_user", {}, SimpleNamespace(sqlstate="P0009"))  # type: ignore[arg-type]
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(side_effect=error))

	db = _RegisterDb()

	with pytest.raises(DBAPIError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), db)  # type: ignore[arg-type]

	assert db.calls == ["db.rollback"]


async def test_record_login_attempt_converts_database_connection_failure_and_rolls_back(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""_record_login_attempt内でcommit時に接続断（sqlstate 08006）が起きた場合、
	ServiceUnavailableErrorへ変換されcommit後にrollbackされることを検証する。
	"""
	monkeypatch.setattr(auth_service.login_history_repository, "create", AsyncMock())
	db = _RegisterDb(OperationalError("login history", {}, SimpleNamespace(sqlstate="08006")))

	with pytest.raises(ServiceUnavailableError):
		await auth_service._record_login_attempt(
			db,
			None,
			"taro",
			_FakeRequest(),
			"session",
			"127.0.0.1",
			success=True,
			failure_reason=None,
		)

	assert db.calls == ["db.commit", "db.rollback"]


@pytest.mark.parametrize("sqlstate", ["08006", "57P03"])
async def test_register_converts_connection_sqlstate_to_service_unavailable(
	monkeypatch: pytest.MonkeyPatch, sqlstate: str
) -> None:
	"""register時のDB接続系エラー（08006/57P03）がServiceUnavailableErrorへ変換されrollbackされることを検証する。"""
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	error = OperationalError("CALL sp_register_user", {}, SimpleNamespace(sqlstate=sqlstate))
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(side_effect=error))
	db = _RegisterDb()

	with pytest.raises(ServiceUnavailableError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), db)  # type: ignore[arg-type]

	assert db.calls == ["db.rollback"]


async def test_login_success_records_history_and_resets_failures(monkeypatch: pytest.MonkeyPatch) -> None:
	"""資格情報が正しい場合にストラテジーへログイン委譲し、login_historyを成功記録・Redis失敗カウントをリセットすることを検証する。"""
	user = _login_user()
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	reset_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", reset_mock)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	history_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", history_mock)
	strategy = _FakeStrategy("session")
	db = _RegisterDb()

	result = await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), db, strategy)  # type: ignore[arg-type]

	assert result == "login-result"
	assert strategy.login_calls == [user]
	reset_mock.assert_awaited_once()
	assert history_mock.await_args.kwargs["success"] is True
	assert history_mock.await_args.kwargs["login_method"] == "session"


async def test_login_rolls_back_auth_state_when_history_write_fails(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""ログイン成功後にlogin_history書き込みが失敗した場合、ストラテジーのrollback_loginが呼ばれ、ServiceUnavailableErrorへ変換されログにパスワードが含まれないことを検証する。"""
	user = _login_user()
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	monkeypatch.setattr(
		auth_service.login_history_repository,
		"create",
		AsyncMock(side_effect=DBAPIError("INSERT login_history", {}, Exception())),
	)
	strategy = _FakeStrategy("session")

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(ServiceUnavailableError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), strategy)  # type: ignore[arg-type]

	assert len(strategy.login_calls) == 1
	assert len(strategy.rollback_calls) == 1
	record = next(record for record in caplog.records if getattr(record, "event", None) == "login_history_write_failed")
	assert record.failure_reason == "service_unavailable"
	assert record.login_method == "session"
	assert "Passw0rd!" not in caplog.text


async def test_login_returns_service_unavailable_when_auth_state_rollback_fails(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""history書き込み失敗後のrollback_login自体も失敗した場合、二重障害としてauth_state_revoke_failedがログされServiceUnavailableErrorが送出されることを検証する。"""
	user = _login_user()
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	monkeypatch.setattr(
		auth_service.login_history_repository,
		"create",
		AsyncMock(side_effect=DBAPIError("INSERT login_history", {}, Exception())),
	)
	strategy = _FakeStrategy("session")
	strategy.rollback_login = AsyncMock(side_effect=RuntimeError("rollback failed"))  # type: ignore[method-assign]

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(ServiceUnavailableError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), strategy)  # type: ignore[arg-type]

	strategy.rollback_login.assert_awaited_once()
	record = next(record for record in caplog.records if getattr(record, "event", None) == "auth_state_revoke_failed")
	assert record.operation == "login_rollback"


async def test_login_unknown_user_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
	"""存在しないユーザー名でログインした場合にInvalidCredentialsErrorを送出し、Redis失敗カウント増加とuser_id=Noneでの失敗記録が行われることを検証する。"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	incr_mock = AsyncMock(return_value=1)
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", incr_mock)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	history_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", history_mock)
	strategy = _FakeStrategy()

	with pytest.raises(InvalidCredentialsError):
		await auth_service.login("ghost", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), strategy)  # type: ignore[arg-type]

	incr_mock.assert_awaited_once()
	assert strategy.login_calls == []
	assert history_mock.await_args.kwargs["success"] is False
	assert history_mock.await_args.kwargs["user_id"] is None
	assert history_mock.await_args.kwargs["failure_reason"] == "invalid_credentials"


async def test_login_wrong_password_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
	"""パスワードが誤っている場合にInvalidCredentialsErrorを送出し、正しいuser_idとともに失敗理由invalid_credentialsが記録されることを検証する。"""
	user = _login_user()
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", AsyncMock(return_value=1))
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: False)
	history_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", history_mock)

	with pytest.raises(InvalidCredentialsError):
		await auth_service.login("taro", "wrong", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	assert history_mock.await_args.kwargs["user_id"] == user.id
	assert history_mock.await_args.kwargs["failure_reason"] == "invalid_credentials"


async def test_login_oauth_only_account_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
	"""password_hashが未設定のOAuth専用アカウントへパスワードログインを試みた場合、
	InvalidCredentialsErrorが送出され、かつダミーハッシュでの検証(タイミング攻撃対策)が
	実際に行われることを検証する。
	"""
	user = _login_user(password_hash=None)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", AsyncMock(return_value=1))
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	verify_calls: list[tuple[str, str]] = []

	def _verify(plain: str, password_hash: str) -> bool:
		"""verify_passwordの代わりに、呼び出し引数を記録して常にFalseを返すスタブ。"""
		verify_calls.append((plain, password_hash))
		return False

	monkeypatch.setattr(auth_service, "verify_password", _verify)
	monkeypatch.setattr(auth_service.login_history_repository, "create", AsyncMock())

	with pytest.raises(InvalidCredentialsError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	# password未設定でもダミーハッシュで検証し、応答時間差からアカウント種別が漏れないようにする。
	assert verify_calls and verify_calls[0][1] == auth_service.get_dummy_password_hash()


async def test_login_inactive_user_raises_after_password_check(monkeypatch: pytest.MonkeyPatch) -> None:
	"""パスワード自体は正しいが、アカウントが無効化(is_active=False)されている場合に
	UserInactiveErrorが送出され、認証戦略のログイン処理が呼ばれず、
	ログイン履歴のfailure_reasonが"user_inactive"になることを検証する。
	"""
	user = _login_user(is_active=False)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	history_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", history_mock)
	strategy = _FakeStrategy()

	with pytest.raises(UserInactiveError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), strategy)  # type: ignore[arg-type]

	assert strategy.login_calls == []
	assert history_mock.await_args.kwargs["failure_reason"] == "user_inactive"


async def test_login_unverified_email_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""パスワードは正しいがメールアドレスが未認証のユーザーがログインした場合、
	EmailNotVerifiedErrorが送出され、ログイン履歴のfailure_reasonが
	"email_not_verified"になることを検証する。
	"""
	user = _login_user(verified=False)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	history_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", history_mock)

	with pytest.raises(EmailNotVerifiedError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	assert history_mock.await_args.kwargs["failure_reason"] == "email_not_verified"


async def test_login_rate_limited_before_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ログイン失敗回数が上限に達している場合、ユーザー検索(get_by_login_identifier)を
	一切呼び出す前にTooManyAttemptsErrorが送出されることを検証する。
	"""
	settings = auth_service.get_backend_settings()
	monkeypatch.setattr(
		auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=settings.login_max_attempts)
	)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_ttl", AsyncMock(return_value=60))
	lookup_mock = AsyncMock()
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", lookup_mock)

	with pytest.raises(TooManyAttemptsError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	lookup_mock.assert_not_awaited()


async def test_login_rate_limited_emits_structured_log(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""too_many_attempts時もevent=login_attemptが出力される。"""
	settings = auth_service.get_backend_settings()
	monkeypatch.setattr(
		auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=settings.login_max_attempts)
	)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_ttl", AsyncMock(return_value=60))

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(TooManyAttemptsError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	login_attempt_records = [r for r in caplog.records if getattr(r, "event", None) == "login_attempt"]
	assert len(login_attempt_records) == 1
	assert login_attempt_records[0].failure_reason == "too_many_attempts"
	assert "Passw0rd!" not in caplog.text


async def test_login_fails_closed_when_rate_limit_check_raises(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""ensure_login_not_rate_limited内のRedis障害（get_login_failure_countの例外）は503へ変換される。"""
	monkeypatch.setattr(
		auth_service.redis_store,
		"get_login_failure_count",
		AsyncMock(side_effect=RuntimeError("redis down")),
	)
	lookup_mock = AsyncMock()
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", lookup_mock)

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(ServiceUnavailableError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	lookup_mock.assert_not_awaited()
	record = next(record for record in caplog.records if getattr(record, "event", None) == "login_attempt")
	assert record.failure_reason == "service_unavailable"
	assert record.success is False
	assert "Passw0rd!" not in caplog.text


async def test_login_fails_closed_when_record_login_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""不正資格情報検出後のincr_login_failure（Redis）障害は503へ変換される。"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(
		auth_service.redis_store, "incr_login_failure", AsyncMock(side_effect=RuntimeError("redis down"))
	)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	history_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", history_mock)

	with pytest.raises(ServiceUnavailableError):
		await auth_service.login(
			"ghost", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy()
		)  # type: ignore[arg-type]

	history_mock.assert_not_awaited()


async def test_login_fails_closed_when_record_login_success_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	"""資格情報一致後のreset_login_failure（Redis）障害は503へ変換される。"""
	user = _login_user()
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(
		auth_service.redis_store, "reset_login_failure", AsyncMock(side_effect=RuntimeError("redis down"))
	)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	strategy = _FakeStrategy()

	with pytest.raises(ServiceUnavailableError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), strategy)  # type: ignore[arg-type]

	assert strategy.login_calls == []


async def test_login_fails_closed_when_login_history_write_raises_on_failure_path(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""失敗系（invalid_credentials）でのDB書き込み障害も503へ変換される。"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", AsyncMock(return_value=1))
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(
		auth_service.login_history_repository,
		"create",
		AsyncMock(side_effect=DBAPIError("INSERT login_history", {}, Exception())),
	)

	with caplog.at_level("WARNING", logger="app.oauth"), pytest.raises(ServiceUnavailableError):
		await auth_service.login(
			"ghost", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy()
		)  # type: ignore[arg-type]

	record = next(record for record in caplog.records if getattr(record, "event", None) == "login_history_write_failed")
	assert record.user_id is None
	assert record.login_method == "session"
	assert record.failure_reason == "service_unavailable"


@pytest.mark.parametrize(
	"user",
	[
		pytest.param(_login_user(is_active=False), id="inactive_user"),
		pytest.param(_login_user(verified=False), id="unverified_email"),
	],
)
async def test_login_history_write_failure_on_account_state_path_is_logged(
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
	user: SimpleNamespace,
) -> None:
	"""アカウント無効・メール未認証それぞれの拒否経路(パスワード検証後にアカウント状態で
	弾かれる経路)でログイン履歴の書き込みが失敗した場合も、ServiceUnavailableErrorが
	送出され、app.oauthロガーへlogin_history_write_failedイベントとして
	user_id/login_method/failure_reasonが記録されることを検証する。
	"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	monkeypatch.setattr(
		auth_service.login_history_repository,
		"create",
		AsyncMock(side_effect=DBAPIError("INSERT login_history", {}, Exception())),
	)

	with caplog.at_level("WARNING", logger="app.oauth"), pytest.raises(ServiceUnavailableError) as exc_info:
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	assert isinstance(exc_info.value, ServiceUnavailableError)
	record = next(record for record in caplog.records if getattr(record, "event", None) == "login_history_write_failed")
	assert record.user_id == str(user.id)
	assert record.login_method == "session"
	assert record.failure_reason == "service_unavailable"


async def test_login_fails_closed_when_user_lookup_raises(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""ユーザー検索がServiceUnavailableErrorを送出した場合、ログインはそのまま
	ServiceUnavailableErrorとして失敗し(フェイルクローズ)、login_attemptログの
	failure_reasonが"service_unavailable"となり、user_idはNoneで
	入力されたユーザー名("ghost")がログに残らないことを検証する。
	"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(
		auth_service.user_repository,
		"get_by_login_identifier",
		AsyncMock(side_effect=ServiceUnavailableError()),
	)

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(ServiceUnavailableError):
		await auth_service.login(
			"ghost", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy()
		)  # type: ignore[arg-type]

	record = next(record for record in caplog.records if getattr(record, "event", None) == "login_attempt")
	assert record.failure_reason == "service_unavailable"
	assert record.user_id is None
	assert record.success is False
	assert "ghost" not in caplog.text


async def test_login_propagates_non_connection_user_lookup_operational_error(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""ユーザー検索が接続エラー以外のsqlstate(40P01: デッドロック)を持つOperationalErrorを
	送出した場合、ServiceUnavailableErrorへ変換せず元の例外をそのまま再送出し、
	login_attemptログも出力しないことを検証する。
	"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(
		auth_service.user_repository,
		"get_by_login_identifier",
		AsyncMock(side_effect=OperationalError("SELECT user", {}, SimpleNamespace(sqlstate="40P01"))),
	)

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(OperationalError):
		await auth_service.login(
			"ghost", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy()
		)  # type: ignore[arg-type]

	assert not [record for record in caplog.records if getattr(record, "event", None) == "login_attempt"]


@pytest.mark.parametrize(
	"error",
	[
		InterfaceError("SELECT user", {}, Exception("connection lost")),
		OperationalError("SELECT user", {}, SimpleNamespace(sqlstate="08006")),
		SQLAlchemyTimeoutError("connection pool timeout"),
		DisconnectionError("connection invalidated"),
	],
	ids=["interface", "connection_operational", "pool_timeout", "disconnection"],
)
async def test_login_logs_and_fails_closed_for_connection_user_lookup_errors(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
	"""ユーザー検索がDB接続断・接続プールタイムアウト・切断など各種の接続系エラー
	(InterfaceError/sqlstate 08006のOperationalError/SQLAlchemyTimeoutError/
	DisconnectionError)を送出した場合、いずれもServiceUnavailableErrorへ変換されて
	フェイルクローズすることを検証する。
	"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(
		auth_service.user_repository,
		"get_by_login_identifier",
		AsyncMock(side_effect=error),
	)

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(ServiceUnavailableError):
		await auth_service.login(
			"ghost", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy()
		)  # type: ignore[arg-type]

	record = next(record for record in caplog.records if getattr(record, "event", None) == "login_attempt")
	assert record.failure_reason == "service_unavailable"
	assert record.user_id is None
	assert record.success is False
	assert "ghost" not in caplog.text


async def test_login_fails_closed_when_strategy_login_raises(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""strategy.login()自体の障害（セッション/JWT基盤の障害）も503へ変換される。"""
	user = _login_user()
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	strategy = _FakeStrategy()
	strategy.login = AsyncMock(side_effect=RuntimeError("session backend down"))  # type: ignore[method-assign]
	history_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", history_mock)

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(ServiceUnavailableError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), strategy)  # type: ignore[arg-type]

	history_mock.assert_not_awaited()
	record = next(record for record in caplog.records if getattr(record, "event", None) == "login_attempt")
	assert record.failure_reason == "service_unavailable"
	assert record.user_id == str(user.id)
	assert record.success is False
	assert "session backend down" not in caplog.text
	assert "Passw0rd!" not in caplog.text


async def test_login_attempt_structured_log_emitted_on_success(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""成功時にevent=login_attemptが出力され、パスワードが含まれないこと。"""
	user = _login_user()
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	monkeypatch.setattr(auth_service.login_history_repository, "create", AsyncMock())
	strategy = _FakeStrategy("session")

	with caplog.at_level("INFO", logger="app.oauth"):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), strategy)  # type: ignore[arg-type]

	login_attempt_records = [r for r in caplog.records if getattr(r, "event", None) == "login_attempt"]
	assert len(login_attempt_records) == 1
	record = login_attempt_records[0]
	assert record.success is True
	assert record.auth_mode == "session"
	assert record.user_id == str(user.id)
	assert len(record.identifier) == 64
	assert record.identifier != "taro"
	assert "Passw0rd!" not in caplog.text


@pytest.mark.parametrize(
	("setup_name", "expected_failure_reason", "exc_type"),
	[
		("invalid_credentials", "invalid_credentials", InvalidCredentialsError),
		("user_inactive", "user_inactive", UserInactiveError),
		("email_not_verified", "email_not_verified", EmailNotVerifiedError),
	],
)
async def test_login_attempt_structured_log_emitted_on_failure(
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
	setup_name: str,
	expected_failure_reason: str,
	exc_type: type[Exception],
) -> None:
	"""各失敗理由でevent=login_attemptが出力され、パスワードが含まれないこと。"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", AsyncMock(return_value=1))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.login_history_repository, "create", AsyncMock())

	if setup_name == "invalid_credentials":
		monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
		password = "wrong"
	elif setup_name == "user_inactive":
		user = _login_user(is_active=False)
		monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
		monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
		password = "Passw0rd!"
	else:
		user = _login_user(verified=False)
		monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
		monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
		password = "Passw0rd!"

	with caplog.at_level("INFO", logger="app.oauth"), pytest.raises(exc_type):
		await auth_service.login("taro", password, _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	login_attempt_records = [r for r in caplog.records if getattr(r, "event", None) == "login_attempt"]
	assert len(login_attempt_records) == 1
	record = login_attempt_records[0]
	assert record.success is False
	assert record.failure_reason == expected_failure_reason
	assert "Passw0rd!" not in caplog.text
	assert "wrong" not in caplog.text


async def test_logout_delegates_to_strategy() -> None:
	"""auth_service.logoutが認証戦略(strategy)のlogout処理へ委譲され、1回呼ばれることを検証する。"""
	strategy = _FakeStrategy()

	await auth_service.logout(_FakeRequest(), SimpleNamespace(), strategy)  # type: ignore[arg-type]

	assert strategy.logout_calls == 1


async def test_register_missing_user_after_insert_is_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ユーザー作成(create)は成功したにもかかわらず、直後のget_by_idで
	作成したはずのユーザーが取得できない(None)場合、ServiceUnavailableErrorが
	送出され、メール確認トークンの発行(issue_email_verify_token)が
	呼ばれないことを検証する。
	"""
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(return_value=uuid4()))
	monkeypatch.setattr(auth_service.user_repository, "update_profile", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=None))
	issue_mock = AsyncMock()
	monkeypatch.setattr(email_verification_service, "issue_email_verify_token", issue_mock)

	with pytest.raises(ServiceUnavailableError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]

	issue_mock.assert_not_awaited()


async def test_refresh_delegates_to_strategy() -> None:
	"""auth_service.refreshが認証戦略(strategy)のrefresh処理へ委譲され、
	その戻り値をそのまま返し、1回呼ばれることを検証する。
	"""

	class _RefreshStrategy:
		"""refresh呼び出し回数を記録し固定文字列を返すダミー認証戦略。"""

		def __init__(self) -> None:
			"""呼び出し回数カウンタを0で初期化する。"""
			self.calls = 0

		async def refresh(self, _request: object, _response: object) -> str:
			"""呼び出し回数を1増やし、固定文字列"refreshed"を返す。"""
			self.calls += 1
			return "refreshed"

	strategy = _RefreshStrategy()

	result = await auth_service.refresh(_FakeRequest(), SimpleNamespace(), strategy)  # type: ignore[arg-type]

	assert result == "refreshed"
	assert strategy.calls == 1


async def test_refresh_propagates_not_supported_in_session_mode() -> None:
	"""セッション認証モードの戦略がNotSupportedInModeErrorを送出する場合、
	auth_service.refreshがその例外をそのまま伝播させることを検証する。
	"""

	class _SessionStrategy:
		"""refreshが常にNotSupportedInModeErrorを送出するダミーのセッション認証戦略。"""

		async def refresh(self, _request: object, _response: object) -> None:
			"""セッション認証モードではリフレッシュ非対応であることを示す例外を送出する。"""
			raise NotSupportedInModeError()

	with pytest.raises(NotSupportedInModeError):
		await auth_service.refresh(_FakeRequest(), SimpleNamespace(), _SessionStrategy())  # type: ignore[arg-type]

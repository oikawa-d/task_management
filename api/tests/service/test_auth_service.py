from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import (
	DuplicateEmailError,
	DuplicateUsernameError,
	EmailNotVerifiedError,
	InvalidCredentialsError,
	InvalidResetTokenError,
	InvalidVerifyTokenError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	UserInactiveError,
)
from app.service import auth_service
from sqlalchemy.exc import DBAPIError


class _FakeBackgroundTasks:
	def __init__(self) -> None:
		self.tasks: list[tuple[object, tuple[object, ...]]] = []

	def add_task(self, func: object, *args: object) -> None:
		self.tasks.append((func, args))


class _FakeDb:
	def __init__(self, calls: list[str] | None = None) -> None:
		self.calls = calls if calls is not None else []

	async def commit(self) -> None:
		self.calls.append("db.commit")


def _user(*, verified: bool = False, email: str = "taro@example.com"):
	return SimpleNamespace(id=uuid4(), email=email, email_verified_at="2026-01-01T00:00:00+09:00" if verified else None)


async def test_issue_email_verify_token_replaces_old_and_schedules_mail(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	replace_mock = AsyncMock()
	sent_mock = AsyncMock(return_value=True)
	monkeypatch.setattr(auth_service.redis_store, "replace_email_verify_token", replace_mock)
	monkeypatch.setattr(auth_service.redis_store, "mark_email_verify_sent", sent_mock)
	background = _FakeBackgroundTasks()

	await auth_service.issue_email_verify_token(user, background)  # type: ignore[arg-type]

	replace_mock.assert_awaited_once()
	assert replace_mock.await_args.args[1] == user.id
	sent_mock.assert_awaited_once()
	assert len(background.tasks) == 1
	func, args = background.tasks[0]
	assert func is auth_service.mail_service.send_email_verification_mail
	assert args[0] == user.email
	assert args[2] == auth_service.get_backend_settings().email_verify_ttl_seconds // 3600


async def test_verify_email_success(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	monkeypatch.setattr(auth_service.redis_store, "consume_email_verify_token", AsyncMock(return_value=user_id))
	mark_verified_mock = AsyncMock()
	monkeypatch.setattr(auth_service.user_repository, "mark_email_verified", mark_verified_mock)

	await auth_service.verify_email("token", _FakeDb())  # type: ignore[arg-type]

	mark_verified_mock.assert_awaited_once()
	assert mark_verified_mock.await_args.args[1] == user_id


async def test_verify_email_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(auth_service.redis_store, "consume_email_verify_token", AsyncMock(return_value=None))

	with pytest.raises(InvalidVerifyTokenError):
		await auth_service.verify_email("bad-token", _FakeDb())  # type: ignore[arg-type]


async def test_verify_email_token_reuse_fails(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	consume_mock = AsyncMock(side_effect=[user_id, None])
	monkeypatch.setattr(auth_service.redis_store, "consume_email_verify_token", consume_mock)
	monkeypatch.setattr(auth_service.user_repository, "mark_email_verified", AsyncMock())

	await auth_service.verify_email("token", _FakeDb())  # type: ignore[arg-type]
	with pytest.raises(InvalidVerifyTokenError):
		await auth_service.verify_email("token", _FakeDb())  # type: ignore[arg-type]


async def test_resend_verification_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service.redis_store, "mark_email_verify_sent", AsyncMock(return_value=False))
	replace_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "replace_email_verify_token", replace_mock)
	background = _FakeBackgroundTasks()

	await auth_service.resend_verification("taro@example.com", background, _FakeDb())  # type: ignore[arg-type]

	replace_mock.assert_not_awaited()
	assert background.tasks == []


async def test_resend_verification_already_verified_noop(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user(verified=True)
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	sent_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "mark_email_verify_sent", sent_mock)
	background = _FakeBackgroundTasks()

	await auth_service.resend_verification("taro@example.com", background, _FakeDb())  # type: ignore[arg-type]

	sent_mock.assert_not_awaited()
	assert background.tasks == []


async def test_resend_verification_unknown_user_noop(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	sent_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "mark_email_verify_sent", sent_mock)
	background = _FakeBackgroundTasks()

	await auth_service.resend_verification("unknown@example.com", background, _FakeDb())  # type: ignore[arg-type]

	sent_mock.assert_not_awaited()
	assert background.tasks == []


async def test_resend_verification_issues_new_token_when_interval_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service.redis_store, "mark_email_verify_sent", AsyncMock(return_value=True))
	replace_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "replace_email_verify_token", replace_mock)
	background = _FakeBackgroundTasks()

	await auth_service.resend_verification("taro@example.com", background, _FakeDb())  # type: ignore[arg-type]

	replace_mock.assert_awaited_once()
	assert len(background.tasks) == 1


async def test_request_password_reset_unknown_email_noop(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	save_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "save_password_reset_token", save_mock)
	background = _FakeBackgroundTasks()

	await auth_service.request_password_reset("unknown@example.com", background, _FakeDb())  # type: ignore[arg-type]

	save_mock.assert_not_awaited()
	assert background.tasks == []


async def test_request_password_reset_success_schedules_mail(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	save_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "save_password_reset_token", save_mock)
	background = _FakeBackgroundTasks()

	await auth_service.request_password_reset("taro@example.com", background, _FakeDb())  # type: ignore[arg-type]

	save_mock.assert_awaited_once()
	assert save_mock.await_args.args[1] == user.id
	assert len(background.tasks) == 1
	func, args = background.tasks[0]
	assert func is auth_service.mail_service.send_password_reset_mail
	assert args[2] == auth_service.get_backend_settings().password_reset_ttl_seconds // 60


async def test_reset_password_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(auth_service.redis_store, "consume_password_reset_token", AsyncMock(return_value=None))
	delete_sessions_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "delete_all_sessions", delete_sessions_mock)

	with pytest.raises(InvalidResetTokenError):
		await auth_service.reset_password("bad-token", "NewPassw0rd!", _FakeDb())  # type: ignore[arg-type]

	delete_sessions_mock.assert_not_awaited()


async def test_reset_password_revokes_all_sessions_before_db_update(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	call_order: list[str] = []

	async def _consume(token: str) -> object:
		call_order.append("consume_password_reset_token")
		return user_id

	async def _delete_sessions(uid: object) -> int:
		call_order.append("delete_all_sessions")
		return 1

	async def _revoke_refresh(uid: object) -> int:
		call_order.append("revoke_all_refresh_tokens")
		return 1

	async def _update_password(db: object, uid: object, password_hash: str) -> None:
		call_order.append("update_password")

	monkeypatch.setattr(auth_service.redis_store, "consume_password_reset_token", _consume)
	monkeypatch.setattr(auth_service.redis_store, "delete_all_sessions", _delete_sessions)
	monkeypatch.setattr(auth_service.redis_store, "revoke_all_refresh_tokens", _revoke_refresh)
	monkeypatch.setattr(auth_service.user_repository, "update_password", _update_password)
	monkeypatch.setattr(auth_service, "hash_password", lambda new_password: f"hashed:{new_password}")

	db = _FakeDb(call_order)
	await auth_service.reset_password("token", "NewPassw0rd!", db)  # type: ignore[arg-type]

	assert call_order == [
		"consume_password_reset_token",
		"delete_all_sessions",
		"revoke_all_refresh_tokens",
		"update_password",
		"db.commit",
	]


class _FakeRequest:
	def __init__(self, headers: dict[str, str] | None = None) -> None:
		self.headers = headers or {}
		self.client = SimpleNamespace(host="203.0.113.10")
		self.state = SimpleNamespace()


class _FakeStrategy:
	def __init__(self, mode: str = "session") -> None:
		self.mode = mode
		self.login_calls: list[object] = []
		self.logout_calls = 0

	async def login(self, user: object, _request: object, _response: object) -> str:
		self.login_calls.append(user)
		return "login-result"

	async def logout(self, _request: object, _response: object) -> None:
		self.logout_calls += 1


class _RegisterDb:
	def __init__(self) -> None:
		self.calls: list[str] = []

	async def commit(self) -> None:
		self.calls.append("db.commit")

	async def rollback(self) -> None:
		self.calls.append("db.rollback")


def _register_payload(**overrides: object) -> auth_service.RegisterRequest:
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


def _patch_register_rate_limit(monkeypatch: pytest.MonkeyPatch, count: int = 1) -> None:
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=count))


def _login_user(*, is_active: bool = True, verified: bool = True, password_hash: str | None = "hash"):
	return SimpleNamespace(
		id=uuid4(),
		username="taro",
		email="taro@example.com",
		password_hash=password_hash,
		is_active=is_active,
		email_verified_at="2026-01-01T00:00:00+09:00" if verified else None,
	)


async def test_register_creates_user_and_schedules_verification(monkeypatch: pytest.MonkeyPatch) -> None:
	_patch_register_rate_limit(monkeypatch)
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
	monkeypatch.setattr(auth_service, "issue_email_verify_token", issue_mock)
	db = _RegisterDb()

	user = await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), db)  # type: ignore[arg-type]

	assert user is created
	assert db.calls == ["db.commit"]
	assert create_mock.await_args.args[1] == "taro"
	# 平文パスワードは保存しない（argon2idハッシュのみを渡す）。
	assert create_mock.await_args.args[3] != "Passw0rd!"
	update_profile_mock.assert_awaited_once()
	issue_mock.assert_awaited_once()


async def test_register_duplicate_username_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	_patch_register_rate_limit(monkeypatch)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=object()))
	create_mock = AsyncMock()
	monkeypatch.setattr(auth_service.user_repository, "create", create_mock)

	with pytest.raises(DuplicateUsernameError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]

	create_mock.assert_not_awaited()


async def test_register_duplicate_email_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	_patch_register_rate_limit(monkeypatch)
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
	_patch_register_rate_limit(monkeypatch)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	error = DBAPIError("CALL sp_register_user", {}, SimpleNamespace(sqlstate=sqlstate))  # type: ignore[arg-type]
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(side_effect=error))
	db = _RegisterDb()

	with pytest.raises(expected):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), db)  # type: ignore[arg-type]

	assert db.calls == ["db.rollback"]


async def test_register_reraises_unknown_sqlstate(monkeypatch: pytest.MonkeyPatch) -> None:
	_patch_register_rate_limit(monkeypatch)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	error = DBAPIError("CALL sp_register_user", {}, SimpleNamespace(sqlstate="P0009"))  # type: ignore[arg-type]
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(side_effect=error))

	with pytest.raises(DBAPIError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]


async def test_register_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = auth_service.get_backend_settings()
	_patch_register_rate_limit(monkeypatch, count=settings.rate_limit_register_max_requests + 1)
	lookup_mock = AsyncMock()
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", lookup_mock)

	with pytest.raises(TooManyAttemptsError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]

	lookup_mock.assert_not_awaited()


async def test_login_success_records_history_and_resets_failures(monkeypatch: pytest.MonkeyPatch) -> None:
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


async def test_login_unknown_user_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
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
	assert history_mock.await_args.kwargs["failure_reason"] == "INVALID_CREDENTIALS"


async def test_login_wrong_password_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
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


async def test_login_oauth_only_account_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _login_user(password_hash=None)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", AsyncMock(return_value=1))
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	verify_calls: list[tuple[str, str]] = []

	def _verify(plain: str, password_hash: str) -> bool:
		verify_calls.append((plain, password_hash))
		return False

	monkeypatch.setattr(auth_service, "verify_password", _verify)
	monkeypatch.setattr(auth_service.login_history_repository, "create", AsyncMock())

	with pytest.raises(InvalidCredentialsError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	# password未設定でもダミーハッシュで検証し、応答時間差からアカウント種別が漏れないようにする。
	assert verify_calls and verify_calls[0][1] == auth_service.get_dummy_password_hash()


async def test_login_inactive_user_raises_after_password_check(monkeypatch: pytest.MonkeyPatch) -> None:
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
	assert history_mock.await_args.kwargs["failure_reason"] == "USER_INACTIVE"


async def test_login_unverified_email_raises(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _login_user(verified=False)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
	history_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", history_mock)

	with pytest.raises(EmailNotVerifiedError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	assert history_mock.await_args.kwargs["failure_reason"] == "EMAIL_NOT_VERIFIED"


async def test_login_rate_limited_before_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = auth_service.get_backend_settings()
	monkeypatch.setattr(
		auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=settings.login_max_attempts)
	)
	lookup_mock = AsyncMock()
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", lookup_mock)

	with pytest.raises(TooManyAttemptsError):
		await auth_service.login("taro", "Passw0rd!", _FakeRequest(), SimpleNamespace(), _RegisterDb(), _FakeStrategy())  # type: ignore[arg-type]

	lookup_mock.assert_not_awaited()


async def test_logout_delegates_to_strategy() -> None:
	strategy = _FakeStrategy()

	await auth_service.logout(_FakeRequest(), SimpleNamespace(), strategy)  # type: ignore[arg-type]

	assert strategy.logout_calls == 1


async def test_register_redis_failure_is_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", AsyncMock(side_effect=RuntimeError("redis down")))

	with pytest.raises(ServiceUnavailableError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]


async def test_register_missing_user_after_insert_is_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
	_patch_register_rate_limit(monkeypatch)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service.user_repository, "create", AsyncMock(return_value=uuid4()))
	monkeypatch.setattr(auth_service.user_repository, "update_profile", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=None))
	issue_mock = AsyncMock()
	monkeypatch.setattr(auth_service, "issue_email_verify_token", issue_mock)

	with pytest.raises(ServiceUnavailableError):
		await auth_service.register(_register_payload(), _FakeBackgroundTasks(), _FakeRequest(), _RegisterDb())  # type: ignore[arg-type]

	issue_mock.assert_not_awaited()

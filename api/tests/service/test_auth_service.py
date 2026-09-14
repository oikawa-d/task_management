import logging
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
from uuid import uuid4

import pytest
from app.auth.base import LoginResult
from app.core.exceptions import (
	DuplicateEmailError,
	DuplicateUsernameError,
	EmailNotVerifiedError,
	InvalidCredentialsError,
	InvalidResetTokenError,
	InvalidVerifyTokenError,
	UserInactiveError,
)
from app.schemas.auth import CurrentUser, RegisterRequest
from app.service import auth_service
from fastapi import Request, Response
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

	async def rollback(self) -> None:
		self.calls.append("db.rollback")


def _request() -> Request:
	return Request(
		{
			"type": "http",
			"method": "POST",
			"path": "/api/auth/login",
			"headers": [(b"user-agent", b"pytest")],
			"client": ("127.0.0.1", 1234),
			"server": ("localhost", 8000),
			"scheme": "http",
		}
	)


def _settings(**overrides: object) -> SimpleNamespace:
	values: dict[str, object] = {
		"auth_mode": "session",
		"trusted_proxy_cidrs": [],
		"login_max_attempts": 5,
		"login_lock_window_seconds": 900,
		"rate_limit_register_max_requests": 5,
		"rate_limit_register_window_seconds": 900,
		"google_login_enabled": True,
		"google_client_id": "client-id",
		"google_client_secret": "client-secret",
		"cookie_name_csrf": "cerberus_csrf",
		"email_verify_ttl_seconds": 86400,
		"email_verify_resend_interval_seconds": 60,
	}
	values.update(overrides)
	return SimpleNamespace(**values)


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


async def test_register_does_not_login_and_schedules_verification_mail(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	user_id = uuid4()
	user = SimpleNamespace(id=user_id, email="taro@example.com")
	payload = RegisterRequest(
		username="taro",
		email="taro@example.com",
		password="Password1!",
		password_confirm="Password1!",
		last_name="山田",
		first_name="太郎",
		last_name_kana="ヤマダ",
		first_name_kana="タロウ",
		birth_date=date(1995, 4, 1),
	)
	create_mock = AsyncMock(return_value=user_id)
	monkeypatch.setattr(auth_service.user_repository, "create", create_mock)
	monkeypatch.setattr(auth_service.user_repository, "update_profile", AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(auth_service, "hash_password", lambda value: f"hashed:{value}")
	verify_mock = AsyncMock()
	monkeypatch.setattr(auth_service, "issue_email_verify_token", verify_mock)

	caplog.set_level(logging.INFO, logger="app.oauth")
	actual = await auth_service.register(payload, _FakeBackgroundTasks(), _request(), _FakeDb())  # type: ignore[arg-type]

	assert actual is user
	assert create_mock.await_count == 1
	verify_mock.assert_awaited_once()
	registered = next(record for record in caplog.records if record.event == "user_registered")
	assert registered.user_id == str(user_id)


@pytest.mark.parametrize(
	("sqlstate", "expected"),
	[("P0001", DuplicateUsernameError), ("P0002", DuplicateEmailError)],
)
async def test_register_translates_duplicate_sqlstate(
	monkeypatch: pytest.MonkeyPatch, sqlstate: str, expected: type[Exception]
) -> None:
	monkeypatch.setattr(
		auth_service.user_repository,
		"create",
		AsyncMock(side_effect=DBAPIError("CALL", {}, SimpleNamespace(sqlstate=sqlstate))),
	)
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	monkeypatch.setattr(auth_service, "hash_password", lambda value: "hash")
	payload = RegisterRequest(
		username="taro",
		email="taro@example.com",
		password="Password1!",
		password_confirm="Password1!",
		last_name="山田",
		first_name="太郎",
		last_name_kana="ヤマダ",
		first_name_kana="タロウ",
		birth_date=date(1995, 4, 1),
	)

	with pytest.raises(expected):
		await auth_service.register(payload, _FakeBackgroundTasks(), _request(), _FakeDb())  # type: ignore[arg-type]


async def test_register_rejects_ip_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = _settings(rate_limit_register_max_requests=5, rate_limit_register_window_seconds=900)
	monkeypatch.setattr(auth_service, "get_backend_settings", lambda: settings)
	check_mock = AsyncMock(return_value=6)
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", check_mock)
	monkeypatch.setattr(auth_service.redis_store, "get_rate_limit_ttl", AsyncMock(return_value=900))
	payload = RegisterRequest(
		username="taro",
		email="taro@example.com",
		password="Password1!",
		password_confirm="Password1!",
		last_name="山田",
		first_name="太郎",
		last_name_kana="ヤマダ",
		first_name_kana="タロウ",
		birth_date=date(1995, 4, 1),
	)

	with pytest.raises(auth_service.TooManyAttemptsError) as raised:
		await auth_service.register(payload, _FakeBackgroundTasks(), _request(), _FakeDb())  # type: ignore[arg-type]

	check_mock.assert_awaited_once_with("register", "127.0.0.1", 5, 900)
	assert raised.value.retry_after == 900


async def test_register_translates_redis_failure_to_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(auth_service, "get_backend_settings", lambda: _settings())
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", AsyncMock(side_effect=RuntimeError("redis down")))

	with pytest.raises(auth_service.ServiceUnavailableError):
		await auth_service.register(
			RegisterRequest(
				username="taro",
				email="taro@example.com",
				password="Password1!",
				password_confirm="Password1!",
				last_name="山田",
				first_name="太郎",
				last_name_kana="ヤマダ",
				first_name_kana="タロウ",
				birth_date=date(1995, 4, 1),
			),
			_FakeBackgroundTasks(),
			_request(),
			_FakeDb(),
		)  # type: ignore[arg-type]


async def test_register_translates_rate_limit_ttl_failure_to_service_unavailable(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(auth_service, "get_backend_settings", lambda: _settings())
	monkeypatch.setattr(auth_service.redis_store, "check_rate_limit", AsyncMock(return_value=6))
	monkeypatch.setattr(
		auth_service.redis_store, "get_rate_limit_ttl", AsyncMock(side_effect=RuntimeError("redis down"))
	)

	with pytest.raises(auth_service.ServiceUnavailableError):
		await auth_service.register(
			RegisterRequest(
				username="taro",
				email="taro@example.com",
				password="Password1!",
				password_confirm="Password1!",
				last_name="山田",
				first_name="太郎",
				last_name_kana="ヤマダ",
				first_name_kana="タロウ",
				birth_date=date(1995, 4, 1),
			),
			_FakeBackgroundTasks(),
			_request(),
			_FakeDb(),
		)  # type: ignore[arg-type]


async def test_login_records_success_and_uses_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(
		id=uuid4(), password_hash="hash", is_active=True, email_verified_at=datetime.now(), email="taro@example.com"
	)
	strategy = SimpleNamespace(
		mode="session", login=AsyncMock(return_value=LoginResult("session")), rollback_login=AsyncMock()
	)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda password, password_hash: True)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	reset_mock = AsyncMock()
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", reset_mock)
	record_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", record_mock)

	actual = await auth_service.login(
		"taro",
		"Password1!",
		_request(),
		Response(),
		_FakeDb(),  # type: ignore[arg-type]
		strategy,
		settings=_settings(),
	)

	assert actual.auth_mode == "session"
	strategy.login.assert_awaited_once()
	reset_mock.assert_awaited_once_with("taro", "127.0.0.1")
	record_mock.assert_awaited_once()


@pytest.mark.parametrize(
	("active", "verified", "expected"),
	[(False, True, UserInactiveError), (True, False, EmailNotVerifiedError)],
)
async def test_login_rejects_ineligible_user_after_password_verification(
	monkeypatch: pytest.MonkeyPatch, active: bool, verified: bool, expected: type[Exception]
) -> None:
	user = SimpleNamespace(
		id=uuid4(), password_hash="hash", is_active=active, email_verified_at=datetime.now() if verified else None
	)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda password, password_hash: True)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	record_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", record_mock)

	with pytest.raises(expected):
		await auth_service.login(
			"taro", "Password1!", _request(), Response(), _FakeDb(), strategy=None, settings=_settings()
		)  # type: ignore[arg-type]

	assert record_mock.await_count == 1


async def test_login_unknown_user_verifies_dummy_hash_and_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=None))
	monkeypatch.setattr(auth_service, "get_dummy_password_hash", lambda: "dummy")

	def verify_mock(password: str, password_hash: str) -> bool:
		return password_hash == "dummy"

	monkeypatch.setattr(auth_service, "verify_password", verify_mock)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", AsyncMock(return_value=1))
	record_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", record_mock)

	with pytest.raises(InvalidCredentialsError):
		await auth_service.login("unknown", "Password1!", _request(), Response(), _FakeDb(), settings=_settings())  # type: ignore[arg-type]

	record_mock.assert_awaited_once()
	assert record_mock.await_args.kwargs["user_id"] is None


async def test_login_rejects_oauth_user_even_if_dummy_hash_matches(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(id=uuid4(), password_hash=None, is_active=True, email_verified_at=datetime.now())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "get_dummy_password_hash", lambda: "dummy")
	monkeypatch.setattr(auth_service, "verify_password", lambda password, password_hash: True)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", AsyncMock(return_value=1))
	record_mock = AsyncMock()
	monkeypatch.setattr(auth_service.login_history_repository, "create", record_mock)

	with pytest.raises(InvalidCredentialsError):
		await auth_service.login("google-user", "Password1!", _request(), Response(), _FakeDb(), settings=_settings())  # type: ignore[arg-type]

	record_mock.assert_awaited_once()
	assert record_mock.await_args.kwargs["failure_reason"] == "invalid_credentials"


async def test_login_rolls_back_auth_state_when_history_record_fails(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	user = SimpleNamespace(id=uuid4(), password_hash="hash", is_active=True, email_verified_at=datetime.now())
	result = LoginResult("session", session_id="session-id")
	strategy = SimpleNamespace(
		mode="session",
		login=AsyncMock(return_value=result),
		rollback_login=AsyncMock(side_effect=RuntimeError("rollback down")),
	)
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda password, password_hash: True)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())
	monkeypatch.setattr(auth_service.login_history_repository, "create", AsyncMock(side_effect=RuntimeError("db down")))

	caplog.set_level(logging.INFO, logger="app.oauth")
	with pytest.raises(auth_service.ServiceUnavailableError):
		await auth_service.login(
			"taro", "Password1!", _request(), Response(), _FakeDb(), strategy, settings=_settings()
		)  # type: ignore[arg-type]

	strategy.rollback_login.assert_awaited_once_with(user, result, ANY)
	events = {record.event for record in caplog.records}
	assert events == {"login_attempt", "login_history_write_failed", "auth_state_revoke_failed"}


async def test_login_rejects_strategy_mode_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(id=uuid4(), password_hash="hash", is_active=True, email_verified_at=datetime.now())
	strategy = SimpleNamespace(mode="session", login=AsyncMock(), rollback_login=AsyncMock())
	monkeypatch.setattr(auth_service.user_repository, "get_by_login_identifier", AsyncMock(return_value=user))
	monkeypatch.setattr(auth_service, "verify_password", lambda password, password_hash: True)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=0))
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", AsyncMock())

	with pytest.raises(auth_service.ServiceUnavailableError):
		await auth_service.login(
			"taro", "Password1!", _request(), Response(), _FakeDb(), strategy, settings=_settings(auth_mode="jwt")
		)  # type: ignore[arg-type]

	strategy.login.assert_not_awaited()


async def test_logout_delegates_to_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
	strategy = SimpleNamespace(logout=AsyncMock())
	request = _request()
	response = Response()

	await auth_service.logout(request, response, strategy)

	strategy.logout.assert_awaited_once_with(request, response)


async def test_get_me_maps_user_and_oauth_providers(monkeypatch: pytest.MonkeyPatch) -> None:
	user = SimpleNamespace(
		id=uuid4(),
		username="taro",
		email="taro@example.com",
		last_name="山田",
		first_name="太郎",
		last_name_kana="ヤマダ",
		first_name_kana="タロウ",
		birth_date=date(1995, 4, 1),
		role="member",
		password_hash="hash",
	)
	monkeypatch.setattr(auth_service.user_repository, "get_by_id", AsyncMock(return_value=user))
	monkeypatch.setattr(
		auth_service.oauth_account_repository,
		"list_by_user_id",
		AsyncMock(return_value=[SimpleNamespace(provider="google")]),
	)
	current = CurrentUser(id=user.id, username=user.username, role=user.role, is_active=True, email_verified_at=None)

	actual = await auth_service.get_me(current, _FakeDb(), _settings(auth_mode="jwt"))  # type: ignore[arg-type]

	assert actual.auth_mode == "jwt"
	assert actual.oauth_providers == ["google"]
	assert actual.profile_completed is True


def test_get_auth_config_exposes_only_public_settings() -> None:
	actual = auth_service.get_auth_config(_settings())

	assert actual.auth_mode == "session"
	assert actual.google_login_enabled is True
	assert actual.csrf_cookie_name == "cerberus_csrf"

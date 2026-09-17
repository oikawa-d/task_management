from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.constants import TOKEN_URLSAFE_LENGTH
from app.core.exceptions import InvalidResetTokenError, InvalidVerifyTokenError, ServiceUnavailableError
from app.service import email_verification_service
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError


class _FakeBackgroundTasks:
	def __init__(self) -> None:
		self.tasks: list[tuple[object, tuple[object, ...]]] = []

	def add_task(self, func: object, *args: object) -> None:
		self.tasks.append((func, args))


class _FakeDb:
	def __init__(self, calls: list[str] | None = None, commit_error: Exception | None = None) -> None:
		self.calls = calls if calls is not None else []
		self.commit_error = commit_error

	async def commit(self) -> None:
		self.calls.append("db.commit")
		if self.commit_error is not None:
			raise self.commit_error

	async def rollback(self) -> None:
		self.calls.append("db.rollback")


def _user(*, verified: bool = False, email: str = "taro@example.com") -> SimpleNamespace:
	return SimpleNamespace(
		id=uuid4(),
		email=email,
		email_verified_at="2026-01-01T00:00:00+09:00" if verified else None,
	)


def test_generate_token_uses_configured_urlsafe_generation_length() -> None:
	token = email_verification_service._generate_token()

	assert len(token) == TOKEN_URLSAFE_LENGTH


@pytest.mark.asyncio
async def test_issue_email_verify_token_replaces_old_and_schedules_mail(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	replace_mock = AsyncMock()
	sent_mock = AsyncMock(return_value=True)
	monkeypatch.setattr(email_verification_service.redis_store, "replace_email_verify_token", replace_mock)
	monkeypatch.setattr(email_verification_service.redis_store, "mark_email_verify_sent", sent_mock)
	background = _FakeBackgroundTasks()

	await email_verification_service.issue_email_verify_token(user, background)  # type: ignore[arg-type]

	replace_mock.assert_awaited_once()
	assert replace_mock.await_args.args[1] == user.id
	sent_mock.assert_awaited_once()
	assert len(background.tasks) == 1


@pytest.mark.asyncio
async def test_issue_email_verify_token_passes_token_and_expiration_to_mail(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	monkeypatch.setattr(email_verification_service, "_generate_token", lambda: "new-token")
	replace_mock = AsyncMock()
	sent_mock = AsyncMock(return_value=True)
	monkeypatch.setattr(email_verification_service.redis_store, "replace_email_verify_token", replace_mock)
	monkeypatch.setattr(email_verification_service.redis_store, "mark_email_verify_sent", sent_mock)
	background = _FakeBackgroundTasks()

	await email_verification_service.issue_email_verify_token(user, background)  # type: ignore[arg-type]

	settings = email_verification_service.get_backend_settings()
	replace_mock.assert_awaited_once_with("new-token", user.id, ttl=settings.email_verify_ttl_seconds)
	sent_mock.assert_awaited_once_with(user.id, interval=settings.email_verify_resend_interval_seconds)
	func, args = background.tasks[0]
	assert func is email_verification_service.mail_service.send_email_verification_mail
	assert args == (user.email, "new-token", settings.email_verify_ttl_seconds // 3600)


@pytest.mark.asyncio
async def test_verify_email_rejects_invalid_or_reused_token(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	consume_mock = AsyncMock(side_effect=[user_id, None])
	monkeypatch.setattr(email_verification_service.redis_store, "consume_email_verify_token", consume_mock)
	monkeypatch.setattr(email_verification_service.user_repository, "mark_email_verified", AsyncMock())

	await email_verification_service.verify_email("token", _FakeDb())  # type: ignore[arg-type]
	with pytest.raises(InvalidVerifyTokenError):
		await email_verification_service.verify_email("token", _FakeDb())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_verify_email_commits_database_update(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	monkeypatch.setattr(
		email_verification_service.redis_store,
		"consume_email_verify_token",
		AsyncMock(return_value=user_id),
	)
	mark_verified = AsyncMock()
	monkeypatch.setattr(email_verification_service.user_repository, "mark_email_verified", mark_verified)
	db = _FakeDb()

	await email_verification_service.verify_email("token", db)  # type: ignore[arg-type]

	mark_verified.assert_awaited_once_with(db, user_id)
	assert db.calls == ["db.commit"]


@pytest.mark.asyncio
async def test_verify_email_converts_database_connection_failure_and_rolls_back(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user_id = uuid4()
	monkeypatch.setattr(
		email_verification_service.redis_store, "consume_email_verify_token", AsyncMock(return_value=user_id)
	)
	restore = AsyncMock()
	monkeypatch.setattr(email_verification_service.redis_store, "restore_email_verify_token", restore)
	monkeypatch.setattr(email_verification_service.user_repository, "mark_email_verified", AsyncMock())
	db = _FakeDb(commit_error=OperationalError("verify email", {}, SimpleNamespace(sqlstate="08006")))

	with pytest.raises(ServiceUnavailableError):
		await email_verification_service.verify_email("token", db)  # type: ignore[arg-type]

	assert db.calls == ["db.commit", "db.rollback"]
	restore.assert_awaited_once_with(
		"token", user_id, ttl=email_verification_service.get_backend_settings().email_verify_ttl_seconds
	)


@pytest.mark.asyncio
async def test_resend_verification_is_noop_for_unknown_verified_or_rate_limited_user(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	background = _FakeBackgroundTasks()
	get_user = AsyncMock(side_effect=[None, _user(verified=True), _user()])
	monkeypatch.setattr(email_verification_service.user_repository, "get_by_email", get_user)
	sent = AsyncMock(return_value=False)
	monkeypatch.setattr(email_verification_service.redis_store, "mark_email_verify_sent", sent)
	replace = AsyncMock()
	monkeypatch.setattr(email_verification_service.redis_store, "replace_email_verify_token", replace)

	await email_verification_service.resend_verification("unknown@example.com", background, _FakeDb())  # type: ignore[arg-type]
	await email_verification_service.resend_verification("verified@example.com", background, _FakeDb())  # type: ignore[arg-type]
	await email_verification_service.resend_verification("taro@example.com", background, _FakeDb())  # type: ignore[arg-type]

	sent.assert_awaited_once()
	replace.assert_not_awaited()
	assert background.tasks == []


@pytest.mark.asyncio
async def test_request_password_reset_is_noop_for_unknown_user(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(email_verification_service.user_repository, "get_by_email", AsyncMock(return_value=None))
	save = AsyncMock()
	monkeypatch.setattr(email_verification_service.redis_store, "save_password_reset_token", save)
	background = _FakeBackgroundTasks()

	await email_verification_service.request_password_reset("unknown@example.com", background, _FakeDb())  # type: ignore[arg-type]

	save.assert_not_awaited()
	assert background.tasks == []


@pytest.mark.asyncio
async def test_request_password_reset_schedules_mail(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	monkeypatch.setattr(email_verification_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	monkeypatch.setattr(email_verification_service, "_generate_token", lambda: "reset-token")
	save = AsyncMock()
	monkeypatch.setattr(email_verification_service.redis_store, "save_password_reset_token", save)
	background = _FakeBackgroundTasks()

	await email_verification_service.request_password_reset("taro@example.com", background, _FakeDb())  # type: ignore[arg-type]

	settings = email_verification_service.get_backend_settings()
	save.assert_awaited_once_with("reset-token", user.id, ttl=settings.password_reset_ttl_seconds)
	func, args = background.tasks[0]
	assert func is email_verification_service.mail_service.send_password_reset_mail
	assert args == (user.email, "reset-token", settings.password_reset_ttl_seconds // 60)


@pytest.mark.asyncio
async def test_request_password_reset_does_not_schedule_mail_when_redis_cas_loses(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = _user()
	monkeypatch.setattr(email_verification_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	monkeypatch.setattr(
		email_verification_service.redis_store, "save_password_reset_token", AsyncMock(return_value=False)
	)
	background = _FakeBackgroundTasks()

	await email_verification_service.request_password_reset("taro@example.com", background, _FakeDb())  # type: ignore[arg-type]

	assert background.tasks == []


@pytest.mark.asyncio
async def test_resend_verification_issues_token_and_schedules_mail_after_interval(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = _user()
	monkeypatch.setattr(email_verification_service.user_repository, "get_by_email", AsyncMock(return_value=user))
	monkeypatch.setattr(email_verification_service, "_generate_token", lambda: "resend-token")
	sent_mock = AsyncMock(side_effect=[True, True])
	replace_mock = AsyncMock()
	monkeypatch.setattr(email_verification_service.redis_store, "mark_email_verify_sent", sent_mock)
	monkeypatch.setattr(email_verification_service.redis_store, "replace_email_verify_token", replace_mock)
	background = _FakeBackgroundTasks()

	await email_verification_service.resend_verification("taro@example.com", background, _FakeDb())  # type: ignore[arg-type]

	settings = email_verification_service.get_backend_settings()
	replace_mock.assert_awaited_once_with("resend-token", user.id, ttl=settings.email_verify_ttl_seconds)
	func, args = background.tasks[0]
	assert func is email_verification_service.mail_service.send_email_verification_mail
	assert args == (user.email, "resend-token", settings.email_verify_ttl_seconds // 3600)


@pytest.mark.asyncio
async def test_reset_password_invalid_token_does_not_revoke_or_update_database(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(
		email_verification_service.redis_store,
		"consume_password_reset_token",
		AsyncMock(return_value=None),
	)
	delete_sessions = AsyncMock()
	revoke_refresh = AsyncMock()
	update_password = AsyncMock()
	monkeypatch.setattr(email_verification_service.redis_store, "delete_all_sessions", delete_sessions)
	monkeypatch.setattr(email_verification_service.redis_store, "revoke_all_refresh_tokens", revoke_refresh)
	monkeypatch.setattr(email_verification_service.user_repository, "update_password", update_password)

	with pytest.raises(InvalidResetTokenError):
		await email_verification_service.reset_password("bad-token", "NewPassw0rd!", _FakeDb())  # type: ignore[arg-type]

	delete_sessions.assert_not_awaited()
	revoke_refresh.assert_not_awaited()
	update_password.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_password_revokes_redis_state_before_db_update(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	calls: list[str] = []

	async def consume(_token: str) -> object:
		calls.append("consume")
		return user_id

	async def delete_sessions(_user_id: object) -> int:
		calls.append("delete_sessions")
		return 1

	async def revoke_refresh(_user_id: object) -> int:
		calls.append("revoke_refresh")
		return 1

	async def update_password(_db: object, _user_id: object, _password_hash: str) -> None:
		calls.append("update_password")

	monkeypatch.setattr(email_verification_service.redis_store, "consume_password_reset_token", consume)
	monkeypatch.setattr(
		email_verification_service.redis_store, "save_password_reset_token", AsyncMock(return_value=True)
	)
	monkeypatch.setattr(email_verification_service.redis_store, "delete_all_sessions", delete_sessions)
	monkeypatch.setattr(email_verification_service.redis_store, "revoke_all_refresh_tokens", revoke_refresh)
	monkeypatch.setattr(email_verification_service.user_repository, "update_password", update_password)
	db = _FakeDb(calls)

	await email_verification_service.reset_password("token", "NewPassw0rd!", db)  # type: ignore[arg-type]

	assert calls == ["consume", "delete_sessions", "revoke_refresh", "update_password", "db.commit"]


@pytest.mark.asyncio
async def test_reset_password_restores_token_when_database_commit_fails(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user_id = uuid4()
	monkeypatch.setattr(
		email_verification_service.redis_store, "consume_password_reset_token", AsyncMock(return_value=user_id)
	)
	restore = AsyncMock(return_value=True)
	monkeypatch.setattr(email_verification_service.redis_store, "save_password_reset_token", restore)
	update_password = AsyncMock()
	monkeypatch.setattr(email_verification_service.user_repository, "update_password", update_password)
	monkeypatch.setattr(email_verification_service.redis_store, "delete_all_sessions", AsyncMock())
	monkeypatch.setattr(email_verification_service.redis_store, "revoke_all_refresh_tokens", AsyncMock())
	db = _FakeDb(commit_error=OperationalError("update password", {}, SimpleNamespace(sqlstate="08006")))

	with pytest.raises(ServiceUnavailableError):
		await email_verification_service.reset_password("token", "NewPassw0rd!", db)  # type: ignore[arg-type]

	update_password.assert_awaited_once()
	restore.assert_awaited_once_with(
		"token", user_id, ttl=email_verification_service.get_backend_settings().password_reset_ttl_seconds
	)


@pytest.mark.asyncio
async def test_reset_password_does_not_update_db_when_redis_revocation_fails(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user_id = uuid4()
	monkeypatch.setattr(
		email_verification_service.redis_store, "consume_password_reset_token", AsyncMock(return_value=user_id)
	)
	monkeypatch.setattr(
		email_verification_service.redis_store,
		"delete_all_sessions",
		AsyncMock(side_effect=RedisConnectionError("redis down")),
	)
	restore = AsyncMock(return_value=True)
	monkeypatch.setattr(email_verification_service.redis_store, "save_password_reset_token", restore)
	update_password = AsyncMock()
	monkeypatch.setattr(email_verification_service.user_repository, "update_password", update_password)
	db = _FakeDb()

	with pytest.raises(RedisConnectionError):
		await email_verification_service.reset_password("token", "NewPassw0rd!", db)  # type: ignore[arg-type]

	update_password.assert_not_awaited()
	assert db.calls == []
	restore.assert_awaited_once_with(
		"token", user_id, ttl=email_verification_service.get_backend_settings().password_reset_ttl_seconds
	)

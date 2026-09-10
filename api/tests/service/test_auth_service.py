from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import InvalidResetTokenError, InvalidVerifyTokenError
from app.service import auth_service


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

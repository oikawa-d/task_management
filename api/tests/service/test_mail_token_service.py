import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import InvalidResetTokenError
from app.service.mail_token_service import MailTokenService


@dataclass
class _Settings:
	email_verify_ttl_seconds: int = 3600
	email_verify_resend_interval_seconds: int = 60
	password_reset_ttl_seconds: int = 1800
	frontend_base_url: str = "https://frontend.example"
	mail_from: str = "no-reply@example.test"


class _Background:
	def __init__(self) -> None:
		self.tasks: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

	def add_task(self, func: object, *args: object, **kwargs: object) -> None:
		self.tasks.append((func, args, kwargs))


@pytest.fixture
def user() -> SimpleNamespace:
	return SimpleNamespace(id=uuid.uuid4(), email="user@example.test", email_verified_at=None, is_active=True)


@pytest.mark.asyncio
async def test_issue_email_verification_token_hashes_stores_and_schedules_mail(user: SimpleNamespace) -> None:
	repository = SimpleNamespace(
		replace_email_verify_token=AsyncMock(),
		mark_email_verify_sent=AsyncMock(return_value=True),
	)
	service = MailTokenService(repository, SimpleNamespace(), settings=_Settings())
	background = _Background()

	with patch("app.service.mail_token_service.secrets.token_urlsafe", return_value="plain-token"):
		await service.issue_email_verification_token(user, background)

	repository.replace_email_verify_token.assert_awaited_once_with("plain-token", user.id, 3600)
	assert len(background.tasks) == 1
	assert "#token=plain-token" in str(background.tasks[0][2]["text_body"])
	assert "?token=plain-token" not in str(background.tasks[0][2]["text_body"])


@pytest.mark.asyncio
async def test_resend_verification_suppresses_unknown_verified_and_rate_limited_users() -> None:
	user = SimpleNamespace(id=uuid.uuid4(), email="user@example.test", email_verified_at=None, is_active=True)
	user_repository = SimpleNamespace(
		get_by_email=AsyncMock(side_effect=[None, SimpleNamespace(email_verified_at=object()), user])
	)
	repository = SimpleNamespace(
		is_email_verify_resend_allowed=AsyncMock(return_value=False),
		replace_email_verify_token=AsyncMock(),
		mark_email_verify_sent=AsyncMock(return_value=True),
	)
	service = MailTokenService(repository, user_repository, settings=_Settings())
	background = _Background()

	await service.resend_verification("missing@example.test", background)
	await service.resend_verification("verified@example.test", background)
	await service.resend_verification("user@example.test", background)

	assert background.tasks == []
	repository.replace_email_verify_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_email_consumes_token_once_and_marks_user_verified(user: SimpleNamespace) -> None:
	repository = SimpleNamespace(consume_email_verify_token=AsyncMock(return_value=user.id))
	user_repository = SimpleNamespace(mark_email_verified=AsyncMock())
	service = MailTokenService(repository, user_repository, settings=_Settings())

	await service.verify_email("verify-token")

	repository.consume_email_verify_token.assert_awaited_once_with("verify-token")
	user_repository.mark_email_verified.assert_awaited_once_with(None, user.id)


@pytest.mark.asyncio
async def test_request_password_reset_stores_token_and_schedules_mail(user: SimpleNamespace) -> None:
	user_repository = SimpleNamespace(get_by_email=AsyncMock(return_value=user))
	repository = SimpleNamespace(save_password_reset_token=AsyncMock())
	service = MailTokenService(repository, user_repository, settings=_Settings())
	background = _Background()

	with patch("app.service.mail_token_service.secrets.token_urlsafe", return_value="reset-token"):
		await service.request_password_reset(user.email, background)

	repository.save_password_reset_token.assert_awaited_once_with("reset-token", user.id, 1800)
	assert "#token=reset-token" in str(background.tasks[0][2]["text_body"])


@pytest.mark.asyncio
async def test_reset_password_consumes_token_hashes_password_and_revokes_all_sessions(user: SimpleNamespace) -> None:
	events: list[str] = []

	async def delete_sessions(user_id: uuid.UUID) -> int:
		events.append("sessions")
		return 2

	async def revoke_refresh_tokens(user_id: uuid.UUID) -> int:
		events.append("refresh_tokens")
		return 3

	async def update_password(db: object, user_id: uuid.UUID, password_hash: str) -> None:
		events.append("password")

	repository = SimpleNamespace(
		consume_password_reset_token=AsyncMock(return_value=user.id),
		delete_all_sessions=delete_sessions,
		revoke_all_refresh_tokens=revoke_refresh_tokens,
	)
	update_password_mock = AsyncMock(side_effect=update_password)
	user_repository = SimpleNamespace(update_password=update_password_mock)
	service = MailTokenService(repository, user_repository, password_hasher=lambda value: f"hash:{value}")

	await service.reset_password("reset-token", "NewPassword1!")

	update_password_mock.assert_awaited_once_with(None, user.id, "hash:NewPassword1!")
	assert events == ["sessions", "refresh_tokens", "password"]


@pytest.mark.asyncio
async def test_reset_password_rejects_expired_or_reused_token_without_side_effects() -> None:
	repository = SimpleNamespace(consume_password_reset_token=AsyncMock(return_value=None))
	user_repository = SimpleNamespace(update_password=AsyncMock())
	service = MailTokenService(repository, user_repository, password_hasher=lambda value: value)

	with pytest.raises(InvalidResetTokenError):
		await service.reset_password("invalid-token", "NewPassword1!")

	user_repository.update_password.assert_not_awaited()

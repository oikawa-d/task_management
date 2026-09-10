from unittest.mock import AsyncMock

import pytest
from app.service import mail_service


@pytest.fixture(autouse=True)
def _clear_jinja_cache():
	mail_service._get_jinja_env.cache_clear()
	yield
	mail_service._get_jinja_env.cache_clear()


async def test_send_email_verification_mail_uses_fragment_url_and_calls_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
	send_mock = AsyncMock()
	monkeypatch.setattr(mail_service.aiosmtplib, "send", send_mock)

	await mail_service.send_email_verification_mail("taro@example.com", "plain-token", expires_hours=24)

	send_mock.assert_awaited_once()
	message = send_mock.await_args.args[0]
	assert message["To"] == "taro@example.com"
	html_body = message.get_body(preferencelist=("html",)).get_content()
	text_body = message.get_body(preferencelist=("plain",)).get_content()
	assert "#token=plain-token" in html_body
	assert "#token=plain-token" in text_body
	assert "?token=" not in html_body
	assert "?token=" not in text_body


async def test_send_password_reset_mail_uses_fragment_url_and_calls_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
	send_mock = AsyncMock()
	monkeypatch.setattr(mail_service.aiosmtplib, "send", send_mock)

	await mail_service.send_password_reset_mail("taro@example.com", "plain-token", expires_minutes=30)

	send_mock.assert_awaited_once()
	message = send_mock.await_args.args[0]
	text_body = message.get_body(preferencelist=("plain",)).get_content()
	assert "#token=plain-token" in text_body
	assert "?token=" not in text_body


async def test_mail_send_failure_is_logged_and_not_propagated(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(mail_service.aiosmtplib, "send", AsyncMock(side_effect=ConnectionError("smtp down")))

	# 送信失敗はログのみで、呼び出し元へは伝播させない。
	await mail_service.send_email_verification_mail("taro@example.com", "plain-token", expires_hours=24)

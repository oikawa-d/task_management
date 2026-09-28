"""app.service.mail_service (メール送信サービス)のテスト。

メール本文のURL形式やSMTP送信呼び出し、送信失敗時のログ出力挙動を検証する。
"""

from unittest.mock import AsyncMock

import pytest
from app.service import mail_service


@pytest.fixture(autouse=True)
def _clear_jinja_cache():
	"""各テスト前後でJinja2テンプレート環境のキャッシュをクリアするfixture。

	テスト間でテンプレートキャッシュが共有されて結果が汚染されるのを防ぐため、
	テスト実行前とyield後(teardown)の両方でキャッシュをクリアする。
	"""
	mail_service._get_jinja_env.cache_clear()
	yield
	mail_service._get_jinja_env.cache_clear()


async def test_send_email_verification_mail_uses_fragment_url_and_calls_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
	"""メールアドレス確認メール送信時に、トークンがフラグメント形式のURLに含まれ、SMTP送信が呼ばれることを検証する。

	HTML本文・プレーンテキスト本文の両方で「#token=」形式が使われ、
	クエリパラメータ形式の「?token=」が含まれないことを確認する。
	"""
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
	"""パスワードリセットメール送信時に、トークンがフラグメント形式のURLに含まれることを検証する。

	プレーンテキスト本文に「#token=」形式のURLが含まれ、
	「?token=」形式が含まれないことを確認する。
	"""
	send_mock = AsyncMock()
	monkeypatch.setattr(mail_service.aiosmtplib, "send", send_mock)

	await mail_service.send_password_reset_mail("taro@example.com", "plain-token", expires_minutes=30)

	send_mock.assert_awaited_once()
	message = send_mock.await_args.args[0]
	text_body = message.get_body(preferencelist=("plain",)).get_content()
	assert "#token=plain-token" in text_body
	assert "?token=" not in text_body


async def test_mail_send_failure_is_logged_without_template_extra(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	"""SMTP送信が例外で失敗した場合に、例外が呼び出し元へ伝播せずログにのみ記録されることを検証する。

	記録されたログレコードに"template"という属性が含まれないことも併せて確認する。
	"""
	monkeypatch.setattr(mail_service.aiosmtplib, "send", AsyncMock(side_effect=ConnectionError("smtp down")))

	# 送信失敗はログのみで、呼び出し元へは伝播させない。
	with caplog.at_level("ERROR", logger="app.mail"):
		await mail_service.send_email_verification_mail("taro@example.com", "plain-token", expires_hours=24)

	record = caplog.records[-1]
	assert not hasattr(record, "template")

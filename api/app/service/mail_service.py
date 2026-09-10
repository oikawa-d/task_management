"""メール認証・パスワードリセットの本文レンダリングとSMTP送信。"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import get_backend_settings

logger = logging.getLogger("app.mail")

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "mail"


@lru_cache
def _get_jinja_env() -> Environment:
	return Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=select_autoescape(["html"]))


def _render(template_prefix: str, context: dict[str, object]) -> tuple[str, str]:
	env = _get_jinja_env()
	html_body = env.get_template(f"{template_prefix}.html").render(**context)
	text_body = env.get_template(f"{template_prefix}.txt").render(**context)
	return html_body, text_body


async def _send_mail(to: str, subject: str, html_body: str, text_body: str) -> None:
	settings = get_backend_settings()
	message = EmailMessage()
	message["From"] = settings.mail_from
	message["To"] = to
	message["Subject"] = subject
	message.set_content(text_body)
	message.add_alternative(html_body, subtype="html")

	try:
		await aiosmtplib.send(
			message,
			hostname=settings.smtp_host,
			port=settings.smtp_port,
			username=settings.smtp_user or None,
			password=settings.smtp_password or None,
			start_tls=settings.smtp_use_tls,
		)
	except Exception:
		# 送信失敗はログのみに留め、呼び出し元（BackgroundTasks）へは伝播させない。
		# トークン平文・ハッシュはログに出力しない。
		logger.error("failed to send mail", extra={"template": subject})


async def send_email_verification_mail(to: str, token: str, expires_hours: int) -> None:
	settings = get_backend_settings()
	verify_url = f"{settings.frontend_base_url}/verify-email#token={token}"
	html_body, text_body = _render("email_verification", {"verify_url": verify_url, "expires_hours": expires_hours})
	await _send_mail(to, "メールアドレスのご確認", html_body, text_body)


async def send_password_reset_mail(to: str, token: str, expires_minutes: int) -> None:
	settings = get_backend_settings()
	reset_url = f"{settings.frontend_base_url}/password/reset#token={token}"
	html_body, text_body = _render("password_reset", {"reset_url": reset_url, "expires_minutes": expires_minutes})
	await _send_mail(to, "パスワード再設定のご案内", html_body, text_body)

import asyncio
import importlib
import logging
import secrets
import smtplib
from email.message import EmailMessage
from typing import Any, Protocol, cast

from fastapi import BackgroundTasks

from app.core.config import TOKEN_URLSAFE_BYTES, BackendSettings, get_backend_settings
from app.core.exceptions import InvalidResetTokenError, InvalidVerifyTokenError

logger = logging.getLogger(__name__)


class MailSender(Protocol):
	async def send(self, *, to: str, subject: str, text_body: str, html_body: str) -> None: ...


class PasswordHasher(Protocol):
	def __call__(self, password: str) -> str: ...


class SmtpMailSender:
	def __init__(self, settings: BackendSettings) -> None:
		self._settings = settings

	async def send(self, *, to: str, subject: str, text_body: str, html_body: str) -> None:
		try:
			await asyncio.to_thread(self._send_sync, to, subject, text_body, html_body)
		except Exception:
			logger.exception("mail delivery failed", extra={"recipient": to})

	def _send_sync(self, to: str, subject: str, text_body: str, html_body: str) -> None:
		message = EmailMessage()
		message["From"] = self._settings.mail_from
		message["To"] = to
		message["Subject"] = subject
		message.set_content(text_body)
		message.add_alternative(html_body, subtype="html")
		with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port) as smtp:
			if self._settings.smtp_use_tls:
				smtp.starttls()
			if self._settings.smtp_user:
				smtp.login(self._settings.smtp_user, self._settings.smtp_password)
			smtp.send_message(message)


def argon2_password_hasher(password: str, settings: BackendSettings | None = None) -> str:
	settings = settings or get_backend_settings()
	argon2 = importlib.import_module("argon2.low_level")
	hashed = argon2.hash_secret(
		password.encode("utf-8"),
		secrets.token_bytes(16),
		time_cost=settings.argon2_time_cost,
		memory_cost=settings.argon2_memory_cost,
		parallelism=settings.argon2_parallelism,
		hash_len=32,
		type=argon2.Type.ID,
	)
	return cast(bytes, hashed).decode("utf-8")


class MailTokenService:
	def __init__(
		self,
		token_repository: Any,
		user_repository: Any,
		settings: BackendSettings | Any | None = None,
		mail_sender: MailSender | None = None,
		password_hasher: PasswordHasher | None = None,
	) -> None:
		self._token_repository = token_repository
		self._user_repository = user_repository
		self._settings = settings or get_backend_settings()
		self._mail_sender = mail_sender or SmtpMailSender(self._settings)
		self._password_hasher = password_hasher or (lambda password: argon2_password_hasher(password, self._settings))

	async def issue_email_verify_token(self, user: Any, background: BackgroundTasks | Any) -> None:
		token = secrets.token_urlsafe(TOKEN_URLSAFE_BYTES)
		allowed = await self._token_repository.mark_email_verify_sent(
			user.id, self._settings.email_verify_resend_interval_seconds
		)
		if not allowed:
			return
		await self._token_repository.replace_email_verify_token(token, user.id, self._settings.email_verify_ttl_seconds)
		await self._schedule_mail(
			background,
			to=user.email,
			subject="メールアドレスの認証",
			text_body=self._verification_text(token),
			html_body=self._verification_html(token),
		)

	async def issue_email_verification_token(self, user: Any, background: BackgroundTasks | Any) -> None:
		await self.issue_email_verify_token(user, background)

	async def verify_email(self, token: str, db: Any = None) -> None:
		user_id = await self._token_repository.consume_email_verify_token(token)
		if user_id is None:
			raise InvalidVerifyTokenError()
		await self._user_repository.mark_email_verified(db, user_id)

	async def resend_verification(self, email: str, background: BackgroundTasks | Any, db: Any = None) -> None:
		user = await self._user_repository.get_by_email(db, email)
		if user is None or user.email_verified_at is not None or not user.is_active:
			return
		if not await self._token_repository.is_email_verify_resend_allowed(user.id):
			return
		await self.issue_email_verify_token(user, background)

	async def request_password_reset(self, email: str, background: BackgroundTasks | Any, db: Any = None) -> None:
		user = await self._user_repository.get_by_email(db, email)
		if user is None or not user.is_active:
			return
		token = secrets.token_urlsafe(TOKEN_URLSAFE_BYTES)
		await self._token_repository.save_password_reset_token(
			token, user.id, self._settings.password_reset_ttl_seconds
		)
		await self._schedule_mail(
			background,
			to=user.email,
			subject="パスワードの再設定",
			text_body=self._reset_text(token),
			html_body=self._reset_html(token),
		)

	async def reset_password(self, token: str, new_password: str, db: Any = None) -> None:
		user_id = await self._token_repository.consume_password_reset_token(token)
		if user_id is None:
			raise InvalidResetTokenError()
		await self._token_repository.delete_all_sessions(user_id)
		await self._token_repository.revoke_all_refresh_tokens(user_id)
		password_hash = self._password_hasher(new_password)
		await self._user_repository.update_password(db, user_id, password_hash)

	async def _schedule_mail(self, background: BackgroundTasks | Any, **message: str) -> None:
		if background is None:
			await self._mail_sender.send(**message)
			return
		background.add_task(self._mail_sender.send, **message)

	def _verification_url(self, token: str) -> str:
		return f"{self._settings.frontend_base_url.rstrip('/')}/verify-email#token={token}"

	def _reset_url(self, token: str) -> str:
		return f"{self._settings.frontend_base_url.rstrip('/')}/password/reset#token={token}"

	def _verification_text(self, token: str) -> str:
		return f"メールアドレスを認証してください。\n{self._verification_url(token)}"

	def _verification_html(self, token: str) -> str:
		return f'<p>メールアドレスを認証してください。</p><a href="{self._verification_url(token)}">認証する</a>'

	def _reset_text(self, token: str) -> str:
		return f"パスワードを再設定してください。\n{self._reset_url(token)}"

	def _reset_html(self, token: str) -> str:
		return f'<p>パスワードを再設定してください。</p><a href="{self._reset_url(token)}">再設定する</a>'

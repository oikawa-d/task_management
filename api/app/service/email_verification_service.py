"""メール認証とパスワード再設定のサービス。"""

from __future__ import annotations

import secrets

from fastapi import BackgroundTasks
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import InvalidResetTokenError, InvalidVerifyTokenError, raise_database_error
from app.core.security import hash_password
from app.models.user import User
from app.repository import redis_store, user_repository
from app.service import mail_service

_TOKEN_URLSAFE_BYTES = 32


def _generate_token() -> str:
	return secrets.token_urlsafe(_TOKEN_URLSAFE_BYTES)


async def issue_email_verify_token(user: User, background: BackgroundTasks) -> None:
	settings = get_backend_settings()
	token = _generate_token()
	await redis_store.replace_email_verify_token(token, user.id, ttl=settings.email_verify_ttl_seconds)
	await redis_store.mark_email_verify_sent(user.id, interval=settings.email_verify_resend_interval_seconds)
	background.add_task(
		mail_service.send_email_verification_mail,
		user.email,
		token,
		settings.email_verify_ttl_seconds // 3600,
	)


async def verify_email(token: str, db: AsyncSession) -> None:
	user_id = await redis_store.consume_email_verify_token(token)
	if user_id is None:
		raise InvalidVerifyTokenError()
	try:
		await user_repository.mark_email_verified(db, user_id)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)


async def resend_verification(email: str, background: BackgroundTasks, db: AsyncSession) -> None:
	user = await user_repository.get_by_email(db, email)
	if user is None or user.email_verified_at is not None:
		return
	settings = get_backend_settings()
	sent = await redis_store.mark_email_verify_sent(user.id, interval=settings.email_verify_resend_interval_seconds)
	if not sent:
		return
	await issue_email_verify_token(user, background)


async def request_password_reset(email: str, background: BackgroundTasks, db: AsyncSession) -> None:
	user = await user_repository.get_by_email(db, email)
	if user is None:
		return
	settings = get_backend_settings()
	token = _generate_token()
	await redis_store.save_password_reset_token(token, user.id, ttl=settings.password_reset_ttl_seconds)
	background.add_task(
		mail_service.send_password_reset_mail,
		user.email,
		token,
		settings.password_reset_ttl_seconds // 60,
	)


async def reset_password(token: str, new_password: str, db: AsyncSession) -> None:
	user_id = await redis_store.consume_password_reset_token(token)
	if user_id is None:
		raise InvalidResetTokenError()

	password_hash = hash_password(new_password)
	await redis_store.delete_all_sessions(user_id)
	await redis_store.revoke_all_refresh_tokens(user_id)
	try:
		await user_repository.update_password(db, user_id, password_hash)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		raise_database_error(exc)

"""ログイン失敗レート制限（ブルートフォース対策）と、メール認証・パスワードリセットのトークン発行・消費オーケストレーション。

参照設計書: docs/detailed_design/auth/06_token_mail.md
"""

from __future__ import annotations

import secrets

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BackendSettings, get_backend_settings
from app.core.exceptions import InvalidResetTokenError, InvalidVerifyTokenError, TooManyAttemptsError
from app.core.security import hash_password
from app.models.user import User
from app.repository import redis_store, user_repository
from app.service import mail_service

# トークン長は設計上固定値だが、桁数変更の余地を残すため1箇所にまとめる（06_token_mail.md §3）。
_TOKEN_URLSAFE_BYTES = 32


async def ensure_login_not_rate_limited(identifier: str, client_ip: str, settings: BackendSettings) -> None:
	"""現在の失敗回数が上限に達している場合は`TooManyAttemptsError`を送出する。"""
	failure_count = await redis_store.get_login_failure_count(identifier, client_ip)
	if failure_count >= settings.login_max_attempts:
		retry_after = max(await redis_store.get_login_failure_ttl(identifier, client_ip), 0)
		raise TooManyAttemptsError(retry_after=retry_after)


async def record_login_failure(identifier: str, client_ip: str, settings: BackendSettings) -> int:
	"""ログイン失敗を記録し、記録後の失敗回数を返す。"""
	return await redis_store.incr_login_failure(identifier, client_ip, settings.login_lock_window_seconds)


async def record_login_success(identifier: str, client_ip: str) -> None:
	"""ログイン成功時に失敗回数カウンタをリセットする。"""
	await redis_store.reset_login_failure(identifier, client_ip)


def _generate_token() -> str:
	return secrets.token_urlsafe(_TOKEN_URLSAFE_BYTES)


async def issue_email_verify_token(user: User, background: BackgroundTasks) -> None:
	"""新しいメール認証tokenを発行し、旧tokenを失効させ、送信を予約する。

	登録時・再送時の両方から呼ばれる共通関数（06_token_mail.md §8.1）。
	"""
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
	"""メール認証tokenをワンタイム消費し、email_verified_atを更新する。"""
	user_id = await redis_store.consume_email_verify_token(token)
	if user_id is None:
		raise InvalidVerifyTokenError()
	await user_repository.mark_email_verified(db, user_id)


async def resend_verification(email: str, background: BackgroundTasks, db: AsyncSession) -> None:
	"""認証メールを再送する。ユーザー不存在・認証済み・レート制限内でも例外を出さない。"""
	user = await user_repository.get_by_email(db, email)
	if user is None or user.email_verified_at is not None:
		return
	settings = get_backend_settings()
	sent = await redis_store.mark_email_verify_sent(user.id, interval=settings.email_verify_resend_interval_seconds)
	if not sent:
		# NX失敗＝直近送信済みで間隔内。再送しない。
		return
	await issue_email_verify_token(user, background)


async def request_password_reset(email: str, background: BackgroundTasks, db: AsyncSession) -> None:
	"""パスワードリセットtokenを発行する。ユーザー不存在でも例外を出さず202を維持する。"""
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
	"""パスワードリセットtokenを消費し、全セッション・全リフレッシュトークンを失効させた上でパスワードを更新する。

	Redisの失効が成功した後にのみDBを更新する（Redis失敗時はDB更新しない）。
	"""
	user_id = await redis_store.consume_password_reset_token(token)
	if user_id is None:
		raise InvalidResetTokenError()
	await redis_store.delete_all_sessions(user_id)
	await redis_store.revoke_all_refresh_tokens(user_id)

	password_hash = hash_password(new_password)
	await user_repository.update_password(db, user_id, password_hash)
	await db.commit()

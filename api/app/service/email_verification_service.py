"""メール認証とパスワード再設定のサービス。"""

from __future__ import annotations

import secrets

from fastapi import BackgroundTasks
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.constants import TOKEN_URLSAFE_BYTES
from app.core.exceptions import (
	InvalidResetTokenError,
	InvalidVerifyTokenError,
	raise_database_error,
)
from app.core.security import hash_password
from app.models.user import User
from app.repository import redis_store, user_repository
from app.service import mail_service


def _generate_token() -> str:
	"""URLセーフなランダムトークンを生成する。

	メール認証・パスワードリセットいずれの一時トークンにも用いる。

	Returns:
		str: `TOKEN_URLSAFE_BYTES`バイト長相当のURLセーフなランダム文字列。
	"""
	return secrets.token_urlsafe(TOKEN_URLSAFE_BYTES)


async def issue_email_verify_token(user: User, background: BackgroundTasks) -> None:
	"""メール認証トークンを発行し、確認メールをバックグラウンドで送信する。

	トークンはRedisにのみ保持し、DBへは書き込まない。メール送信は
	BackgroundTasksに委譲するため、本関数自体はレスポンスをブロックしない。

	Args:
		user: 認証メールを送る対象ユーザー。
		background: メール送信タスクを積むFastAPIのバックグラウンドタスク。

	Returns:
		None
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
	"""メール認証トークンを検証し、ユーザーのメール認証済み状態を確定する。

	Redisからトークンを消費（一度きり利用）した後にDBを更新するため、
	DB更新に失敗した場合はトークンをRedisへ復元し、リトライ可能な状態に戻してから
	例外を送出する。DB更新とコミットが本関数のトランザクション境界であり、
	Redis側の消費はそれより前に完了している非可逆操作である。

	Args:
		token: メール認証用の平文トークン。
		db: ユーザーの認証済みフラグ更新に使用する非同期DBセッション。

	Returns:
		None

	Raises:
		InvalidVerifyTokenError: トークンがRedisに存在しない（無効・期限切れ・使用済み）場合。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	user_id = await redis_store.consume_email_verify_token(token)
	if user_id is None:
		raise InvalidVerifyTokenError()
	try:
		await user_repository.mark_email_verified(db, user_id)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		try:
			settings = get_backend_settings()
			await redis_store.restore_email_verify_token(token, user_id, ttl=settings.email_verify_ttl_seconds)
		except Exception:
			pass
		raise_database_error(exc)


async def resend_verification(email: str, background: BackgroundTasks, db: AsyncSession) -> None:
	"""メール認証の再送を行う。

	ユーザーが存在しない、または既に認証済みの場合は何もしない
	（メール存在有無を外部へ漏らさないため）。再送間隔制限は
	Redisの`mark_email_verify_sent`が担い、間隔内の再送要求は無視する。

	Args:
		email: 再送を要求されたメールアドレス。
		background: メール送信タスクを積むFastAPIのバックグラウンドタスク。
		db: ユーザー検索に使用する非同期DBセッション。

	Returns:
		None
	"""
	user = await user_repository.get_by_email(db, email)
	if user is None or user.email_verified_at is not None:
		return
	settings = get_backend_settings()
	sent = await redis_store.mark_email_verify_sent(user.id, interval=settings.email_verify_resend_interval_seconds)
	if not sent:
		return
	await issue_email_verify_token(user, background)


async def request_password_reset(email: str, background: BackgroundTasks, db: AsyncSession) -> None:
	"""パスワードリセットを申請し、リセットメールをバックグラウンドで送信する。

	ユーザーが存在しない場合や、直近でトークンを発行済みで
	`save_password_reset_token`が保存を拒否した場合は何もしない
	（メールアドレスの存在有無を外部へ漏らさないため）。

	Args:
		email: リセットを申請されたメールアドレス。
		background: メール送信タスクを積むFastAPIのバックグラウンドタスク。
		db: ユーザー検索に使用する非同期DBセッション。

	Returns:
		None
	"""
	user = await user_repository.get_by_email(db, email)
	if user is None:
		return
	settings = get_backend_settings()
	token = _generate_token()
	saved = await redis_store.save_password_reset_token(token, user.id, ttl=settings.password_reset_ttl_seconds)
	if not saved:
		return
	background.add_task(
		mail_service.send_password_reset_mail,
		user.email,
		token,
		settings.password_reset_ttl_seconds // 60,
	)


async def reset_password(token: str, new_password: str, db: AsyncSession) -> None:
	"""パスワードリセットトークンを検証し、パスワードを更新して全セッションを失効させる。

	処理順序はRedis操作が先行しDB更新が後続する。トークン消費後、
	まず全セッション削除・全リフレッシュトークン失効をRedis上で行い、
	いずれかに失敗した場合はトークンを復元して例外を再送出しDB更新には進まない。
	Redis側の失効処理が成功した後にDBのパスワードハッシュを更新してコミットするが、
	この更新に失敗した場合もトークンをRedisへ復元し、リトライ可能な状態に戻す。
	DB更新とコミットが本関数のトランザクション境界である。

	Args:
		token: パスワードリセット用の平文トークン。
		new_password: 設定する新しいパスワード（平文）。
		db: パスワードハッシュ更新に使用する非同期DBセッション。

	Returns:
		None

	Raises:
		InvalidResetTokenError: トークンがRedisに存在しない（無効・期限切れ・使用済み）場合。
		Exception: Redisでのセッション削除・リフレッシュトークン失効に失敗した場合、
			トークンを復元したうえで元の例外をそのまま再送出する。
		app.core.exceptions.AppError: DB更新でSQLSTATEエラーが発生した場合、
			`raise_database_error`により業務例外へ変換されて送出される。
	"""
	user_id = await redis_store.consume_password_reset_token(token)
	if user_id is None:
		raise InvalidResetTokenError()

	password_hash = hash_password(new_password)
	try:
		await redis_store.delete_all_sessions(user_id)
		await redis_store.revoke_all_refresh_tokens(user_id)
	except Exception:
		try:
			settings = get_backend_settings()
			await redis_store.restore_password_reset_token(token, user_id, ttl=settings.password_reset_ttl_seconds)
		except Exception:
			pass
		raise
	try:
		await user_repository.update_password(db, user_id, password_hash)
		await db.commit()
	except DBAPIError as exc:
		await db.rollback()
		try:
			settings = get_backend_settings()
			await redis_store.restore_password_reset_token(token, user_id, ttl=settings.password_reset_ttl_seconds)
		except Exception:
			pass
		raise_database_error(exc)

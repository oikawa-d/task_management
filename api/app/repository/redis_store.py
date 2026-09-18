"""認証・通知で共有するRedisキー操作の公開API。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_backend_settings
from app.redis_client import get_redis_client
from app.repository import redis_store_auth, redis_store_security, redis_store_session
from app.repository.redis_store_common import OAuthHandoffData, OAuthStateData, RefreshData, SessionData, TokenReused

__all__ = [
	"OAuthHandoffData",
	"OAuthStateData",
	"RefreshData",
	"SessionData",
	"TokenReused",
	"check_rate_limit",
	"consume_email_verify_token",
	"consume_oauth_handoff",
	"consume_oauth_state",
	"consume_password_reset_token",
	"create_session",
	"delete_all_sessions",
	"delete_session",
	"get_csrf_token",
	"get_login_failure_count",
	"get_login_failure_ttl",
	"get_rate_limit_ttl",
	"get_refresh_token",
	"get_session",
	"incr_login_failure",
	"mark_email_verify_sent",
	"ping",
	"replace_email_verify_token",
	"restore_password_reset_token",
	"restore_email_verify_token",
	"reset_login_failure",
	"revoke_all_refresh_tokens",
	"revoke_refresh_token",
	"revoke_token_family",
	"rotate_refresh_token",
	"save_oauth_handoff",
	"save_oauth_state",
	"save_password_reset_token",
	"store_refresh_token",
	"touch_session",
]


def _redis() -> Redis:
	"""アプリケーション共有のRedisクライアントを取得する。

	Returns:
		`get_redis_client()`が返す非同期Redisクライアント。
	"""
	return get_redis_client()


def _key_prefix() -> str:
	"""設定済みのRedisキープレフィックスを取得する。

	Returns:
		`get_backend_settings().redis_key_prefix`の値。未設定時は空文字列。
	"""
	return get_backend_settings().redis_key_prefix


async def create_session(user_id: UUID, ip: str | None, ttl: int) -> tuple[str, str]:
	"""`redis_store_session.create_session`への委譲。新規セッションを作成する。

	詳細な副作用・例外は`redis_store_session.create_session`を参照。

	Args:
		user_id: セッションの所有者となるユーザーID。
		ip: セッション作成時の接続元IPアドレス。取得できない場合はNone。
		ttl: セッションの有効期限(秒)。

	Returns:
		(セッションID, CSRFトークン)のタプル。
	"""
	return await redis_store_session.create_session(_redis(), _key_prefix(), user_id, ip, ttl)


async def get_session(session_id: str) -> SessionData | None:
	"""`redis_store_session.get_session`への委譲。セッション情報を取得する。

	Args:
		session_id: 検索対象のセッションID。

	Returns:
		該当するSessionData。存在しない場合はNone。
	"""
	return await redis_store_session.get_session(_redis(), _key_prefix(), session_id)


async def touch_session(session_id: str, user_id: UUID, ttl: int, absolute_expires_at: datetime) -> bool:
	"""`redis_store_session.touch_session`への委譲。セッションの有効期限を延長する。

	Args:
		session_id: 対象のセッションID。
		user_id: セッションの所有者のユーザーID。
		ttl: 延長する有効期限(秒)。
		absolute_expires_at: セッションの絶対有効期限。

	Returns:
		延長できた場合はTrue、セッションが存在しない・絶対有効期限超過の場合はFalse。
	"""
	return await redis_store_session.touch_session(
		_redis(), _key_prefix(), session_id, user_id, ttl, absolute_expires_at
	)


async def get_csrf_token(session_id: str) -> str | None:
	"""`redis_store_session.get_csrf_token`への委譲。CSRFトークンを取得する。

	Args:
		session_id: 対象のセッションID。

	Returns:
		該当するCSRFトークン文字列。存在しない場合はNone。
	"""
	return await redis_store_session.get_csrf_token(_redis(), _key_prefix(), session_id)


async def delete_session(session_id: str, user_id: UUID) -> None:
	"""`redis_store_session.delete_session`への委譲。セッションを削除する。

	Args:
		session_id: 削除対象のセッションID。
		user_id: セッションの所有者のユーザーID。

	Returns:
		None。
	"""
	await redis_store_session.delete_session(_redis(), _key_prefix(), session_id, user_id)


async def delete_all_sessions(user_id: UUID) -> int:
	"""`redis_store_session.delete_all_sessions`への委譲。全セッションを削除する。

	Args:
		user_id: 対象のユーザーID。

	Returns:
		削除したセッションの件数。
	"""
	return await redis_store_session.delete_all_sessions(_redis(), _key_prefix(), user_id)


async def store_refresh_token(token: str, user_id: UUID, family_id: str, ttl: int) -> None:
	"""`redis_store_auth.store_refresh_token`への委譲。リフレッシュトークンを保存する。

	Args:
		token: 保存する生のリフレッシュトークン文字列。
		user_id: トークンの所有者となるユーザーID。
		family_id: トークンローテーションの系列を識別するID。
		ttl: 有効期限(秒)。

	Returns:
		None。
	"""
	await redis_store_auth.store_refresh_token(_redis(), _key_prefix(), token, user_id, family_id, ttl)


async def get_refresh_token(token: str) -> RefreshData | None:
	"""`redis_store_auth.get_refresh_token`への委譲。リフレッシュトークン情報を取得する。

	Args:
		token: 検索対象の生のリフレッシュトークン文字列。

	Returns:
		該当するRefreshData。存在しない場合はNone。
	"""
	return await redis_store_auth.get_refresh_token(_redis(), _key_prefix(), token)


async def rotate_refresh_token(token: str, new_token: str, ttl: int) -> RefreshData | TokenReused | None:
	"""`redis_store_auth.rotate_refresh_token`への委譲。リフレッシュトークンをローテーションする。

	Args:
		token: ローテーション元の生のリフレッシュトークン文字列。
		new_token: ローテーション先の生のリフレッシュトークン文字列。
		ttl: 新トークンの有効期限(秒)。

	Returns:
		成功時はRefreshData、再利用検知時はTokenReused、対象不存在の場合はNone。
	"""
	return await redis_store_auth.rotate_refresh_token(_redis(), _key_prefix(), token, new_token, ttl)


async def revoke_refresh_token(token: str, user_id: UUID) -> None:
	"""`redis_store_auth.revoke_refresh_token`への委譲。リフレッシュトークンを1件失効させる。

	Args:
		token: 失効させる生のリフレッシュトークン文字列。
		user_id: トークンの所有者のユーザーID。

	Returns:
		None。
	"""
	await redis_store_auth.revoke_refresh_token(_redis(), _key_prefix(), token, user_id)


async def revoke_token_family(user_id: UUID, family_id: str, ttl: int | None = None) -> int:
	"""`redis_store_auth.revoke_token_family`への委譲。トークンファミリーを一括失効させる。

	Args:
		user_id: 対象のユーザーID。
		family_id: 失効させるトークンファミリーのID。
		ttl: 失効フラグの有効期限(秒)。指定しない場合はデフォルト値を用いる。

	Returns:
		失効させたトークンの件数。
	"""
	return await redis_store_auth.revoke_token_family(_redis(), _key_prefix(), user_id, family_id, ttl)


async def revoke_all_refresh_tokens(user_id: UUID) -> int:
	"""`redis_store_auth.revoke_all_refresh_tokens`への委譲。全リフレッシュトークンを失効させる。

	Args:
		user_id: 対象のユーザーID。

	Returns:
		失効させたトークンの件数。
	"""
	return await redis_store_auth.revoke_all_refresh_tokens(_redis(), _key_prefix(), user_id)


async def save_oauth_state(state: str, redirect_to: str, code_verifier: str, nonce: str, ttl: int) -> None:
	"""`redis_store_auth.save_oauth_state`への委譲。OAuth state検証用データを保存する。

	Args:
		state: OAuth認可リクエストのstateパラメータ。
		redirect_to: 認可完了後のリダイレクト先。
		code_verifier: PKCE用のcode_verifier。
		nonce: リプレイ攻撃対策用のnonce。
		ttl: 有効期限(秒)。

	Returns:
		None。
	"""
	await redis_store_auth.save_oauth_state(_redis(), _key_prefix(), state, redirect_to, code_verifier, nonce, ttl)


async def consume_oauth_state(state: str) -> OAuthStateData | None:
	"""`redis_store_auth.consume_oauth_state`への委譲。OAuth state検証用データを消費する。

	Args:
		state: 検証対象のstateパラメータ。

	Returns:
		該当するOAuthStateData。存在しない場合はNone。
	"""
	return await redis_store_auth.consume_oauth_state(_redis(), _key_prefix(), state)


async def save_oauth_handoff(code: str, user_id: UUID, redirect_to: str, ttl: int) -> None:
	"""`redis_store_auth.save_oauth_handoff`への委譲。OAuthログイン引き渡しデータを保存する。

	Args:
		code: 引き渡し用のワンタイムコード。
		user_id: ログインが完了したユーザーID。
		redirect_to: 引き渡し完了後のリダイレクト先。
		ttl: 有効期限(秒)。

	Returns:
		None。
	"""
	await redis_store_auth.save_oauth_handoff(_redis(), _key_prefix(), code, user_id, redirect_to, ttl)


async def consume_oauth_handoff(code: str) -> OAuthHandoffData | None:
	"""`redis_store_auth.consume_oauth_handoff`への委譲。OAuthログイン引き渡しデータを消費する。

	Args:
		code: 検証対象のワンタイムコード。

	Returns:
		該当するOAuthHandoffData。存在しない場合はNone。
	"""
	return await redis_store_auth.consume_oauth_handoff(_redis(), _key_prefix(), code)


async def save_password_reset_token(token: str, user_id: UUID, ttl: int) -> bool:
	"""`redis_store_auth.save_password_reset_token`への委譲。パスワードリセットトークンを発行する。

	Args:
		token: 発行する生のパスワードリセットトークン文字列。
		user_id: リセット対象のユーザーID。
		ttl: 有効期限(秒)。

	Returns:
		発行できた場合はTrue、失敗した場合はFalse。
	"""
	return await redis_store_auth.save_password_reset_token(_redis(), _key_prefix(), token, user_id, ttl)


async def consume_password_reset_token(token: str) -> UUID | None:
	"""`redis_store_auth.consume_password_reset_token`への委譲。パスワードリセットトークンを消費する。

	Args:
		token: 消費する生のパスワードリセットトークン文字列。

	Returns:
		トークンに紐づくユーザーID。存在しない・不一致の場合はNone。
	"""
	return await redis_store_auth.consume_password_reset_token(_redis(), _key_prefix(), token)


async def restore_password_reset_token(token: str, user_id: UUID, ttl: int) -> bool:
	"""`redis_store_auth.restore_password_reset_token`への委譲。パスワードリセットトークンを復元する。

	Args:
		token: 復元する生のパスワードリセットトークン文字列。
		user_id: 対象のユーザーID。
		ttl: 有効期限(秒)。

	Returns:
		復元できた場合はTrue、失敗した場合はFalse。
	"""
	return await redis_store_auth.restore_password_reset_token(_redis(), _key_prefix(), token, user_id, ttl)


async def replace_email_verify_token(token: str, user_id: UUID, ttl: int) -> None:
	"""`redis_store_auth.replace_email_verify_token`への委譲。メール確認トークンを差し替える。

	Args:
		token: 発行する生のメール確認トークン文字列。
		user_id: 確認対象のユーザーID。
		ttl: 有効期限(秒)。

	Returns:
		None。
	"""
	await redis_store_auth.replace_email_verify_token(_redis(), _key_prefix(), token, user_id, ttl)


async def consume_email_verify_token(token: str) -> UUID | None:
	"""`redis_store_auth.consume_email_verify_token`への委譲。メール確認トークンを消費する。

	Args:
		token: 消費する生のメール確認トークン文字列。

	Returns:
		トークンに紐づくユーザーID。存在しない場合はNone。
	"""
	return await redis_store_auth.consume_email_verify_token(_redis(), _key_prefix(), token)


async def restore_email_verify_token(token: str, user_id: UUID, ttl: int) -> bool:
	"""`redis_store_auth.restore_email_verify_token`への委譲。メール確認トークンを復元する。

	Args:
		token: 復元する生のメール確認トークン文字列。
		user_id: 対象のユーザーID。
		ttl: 有効期限(秒)。

	Returns:
		復元できた場合はTrue、失敗した場合はFalse。
	"""
	return await redis_store_auth.restore_email_verify_token(_redis(), _key_prefix(), token, user_id, ttl)


async def mark_email_verify_sent(user_id: UUID, interval: int) -> bool:
	"""`redis_store_security.mark_email_verify_sent`への委譲。メール確認送信間隔を制御する。

	Args:
		user_id: 対象のユーザーID。
		interval: 再送を禁止する間隔(秒)。

	Returns:
		送信してよい場合はTrue、間隔内で再送禁止の場合はFalse。
	"""
	return await redis_store_security.mark_email_verify_sent(_redis(), _key_prefix(), user_id, interval)


async def get_login_failure_count(identifier: str, client_ip: str) -> int:
	"""`redis_store_security.get_login_failure_count`への委譲。ログイン失敗回数を取得する。

	Args:
		identifier: ログイン識別子。
		client_ip: クライアントのIPアドレス。

	Returns:
		現在の失敗回数。記録が無い場合は0。
	"""
	return await redis_store_security.get_login_failure_count(_redis(), _key_prefix(), identifier, client_ip)


async def get_login_failure_ttl(identifier: str, client_ip: str) -> int:
	"""`redis_store_security.get_login_failure_ttl`への委譲。ログイン失敗カウンタの残りTTLを取得する。

	Args:
		identifier: ログイン識別子。
		client_ip: クライアントのIPアドレス。

	Returns:
		残りTTL(秒)。キーが存在しない場合は`-2`、TTL未設定の場合は`-1`。
	"""
	return await redis_store_security.get_login_failure_ttl(_redis(), _key_prefix(), identifier, client_ip)


async def incr_login_failure(identifier: str, client_ip: str, window: int) -> int:
	"""`redis_store_security.incr_login_failure`への委譲。ログイン失敗回数を1増加させる。

	Args:
		identifier: ログイン識別子。
		client_ip: クライアントのIPアドレス。
		window: 失敗回数を集計する時間枠(秒)。

	Returns:
		インクリメント後の失敗回数。
	"""
	return await redis_store_security.incr_login_failure(_redis(), _key_prefix(), identifier, client_ip, window)


async def reset_login_failure(identifier: str, client_ip: str) -> None:
	"""`redis_store_security.reset_login_failure`への委譲。ログイン失敗カウンタをリセットする。

	Args:
		identifier: ログイン識別子。
		client_ip: クライアントのIPアドレス。

	Returns:
		None。
	"""
	await redis_store_security.reset_login_failure(_redis(), _key_prefix(), identifier, client_ip)


async def check_rate_limit(scope: str, value: str, max_requests: int, window: int) -> int:
	"""`redis_store_security.check_rate_limit`への委譲。レート制限カウンタをインクリメントする。

	Args:
		scope: レート制限の対象範囲を示す識別子。
		value: 制限対象の値。
		max_requests: 許容する最大リクエスト数(呼び出し元が判定に使用する上限値)。
		window: リクエスト数を集計する時間枠(秒)。

	Returns:
		インクリメント後のリクエスト数。
	"""
	return await redis_store_security.check_rate_limit(_redis(), _key_prefix(), scope, value, max_requests, window)


async def get_rate_limit_ttl(scope: str, value: str) -> int:
	"""`redis_store_security.get_rate_limit_ttl`への委譲。レート制限カウンタの残りTTLを取得する。

	Args:
		scope: レート制限の対象範囲を示す識別子。
		value: 制限対象の値。

	Returns:
		残りTTL(秒、切り上げ)。存在しない・失効済みの場合は0。
	"""
	return await redis_store_security.get_rate_limit_ttl(_redis(), _key_prefix(), scope, value)


async def ping() -> bool:
	"""Redisへの疎通確認を行う。

	Returns:
		Redisからの応答が得られた場合はTrue。
	"""
	return bool(await _redis().ping())

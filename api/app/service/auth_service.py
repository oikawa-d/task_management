"""ログイン失敗レート制限（ブルートフォース対策）。

会員登録・メール認証・パスワードリセットのロジックは本モジュールの担当範囲外。
"""

from __future__ import annotations

from app.core.config import BackendSettings
from app.core.exceptions import TooManyAttemptsError
from app.repository import redis_store


async def ensure_login_not_rate_limited(identifier: str, client_ip: str, settings: BackendSettings) -> None:
	"""現在の失敗回数が上限に達している場合は`TooManyAttemptsError`を送出する。"""
	failure_count = await redis_store.get_login_failure_count(identifier, client_ip)
	if failure_count >= settings.login_max_attempts:
		raise TooManyAttemptsError()


async def record_login_failure(identifier: str, client_ip: str, settings: BackendSettings) -> int:
	"""ログイン失敗を記録し、記録後の失敗回数を返す。"""
	return await redis_store.incr_login_failure(identifier, client_ip, settings.login_lock_window_seconds)


async def record_login_success(identifier: str, client_ip: str) -> None:
	"""ログイン成功時に失敗回数カウンタをリセットする。"""
	await redis_store.reset_login_failure(identifier, client_ip)

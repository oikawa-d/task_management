"""Redis非同期クライアントの生成・クローズ・疎通確認を提供するモジュール。"""

from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_backend_settings


@lru_cache
def get_redis_client() -> Redis:
	"""設定値（接続URL）に基づく非同期Redisクライアントを、プロセス内で1つだけ生成する。

	Returns:
		プロセス内で共有する`Redis`クライアントのシングルトンインスタンス
		（`decode_responses=True`のためレスポンスは文字列で返る）。
	"""
	settings = get_backend_settings()
	client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
	return client


async def close_redis_client() -> None:
	"""アプリ終了時に、共有Redisクライアントの接続を閉じる（`main.py`のlifespanから呼ばれる）。"""
	await get_redis_client().aclose()


async def ping_redis(client: Redis | None = None) -> bool:
	"""Redisへの疎通確認（PINGコマンド）を行う。

	Args:
		client: 疎通確認に使うクライアント。省略時は共有クライアント（`get_redis_client`）を使う。

	Returns:
		応答があればTrue。
	"""
	redis_client = client or get_redis_client()
	return bool(await redis_client.ping())

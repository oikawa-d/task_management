"""batchプロセスのRedis非同期クライアントを管理するモジュール。

実行ロックや通知dedupeなどでbatch全体から共有される単一のRedisクライアントを
モジュールレベルで保持し、生成・取得・破棄の窓口を提供する。
"""

from typing import cast

from redis.asyncio import Redis, from_url

from app.core.config import BatchSettings

_shared_client: Redis | None = None


def create_redis_client(settings: BatchSettings) -> Redis:
	"""設定値から新しい非同期Redisクライアントを生成する。

	Args:
		settings: `redis_url`を含むbatch設定。

	Returns:
		`decode_responses=True`で応答を文字列として扱う新規`Redis`クライアント。
	"""
	return cast(Redis, from_url(settings.redis_url, decode_responses=True))  # type: ignore[no-untyped-call]


def get_redis_client(settings: BatchSettings) -> Redis:
	"""プロセス共有のRedisクライアントを取得する。未生成なら生成する。

	モジュールレベルの`_shared_client`をキャッシュとして使い、
	2回目以降の呼び出しでは同一クライアントを返す。

	Args:
		settings: クライアント未生成時に使用するbatch設定。

	Returns:
		共有される`Redis`クライアント。
	"""
	global _shared_client
	if _shared_client is None:
		_shared_client = create_redis_client(settings)
	return _shared_client


async def close_redis_client(client: Redis | None = None) -> None:
	"""共有Redisクライアントをクローズし、共有参照をリセットする。

	Args:
		client: クローズ対象のクライアント。省略時は共有クライアント（`_shared_client`）を使う。

	副作用:
		呼び出し対象のクライアントが存在すれば非同期に接続を閉じ、
		`_shared_client`をNoneへリセットして次回`get_redis_client`呼び出し時に再生成させる。
	"""
	global _shared_client
	client = client or _shared_client
	if client is not None:
		await client.aclose()
	_shared_client = None


async def ping_redis(client: Redis) -> bool:
	"""Redisへの疎通確認を行う。

	Args:
		client: 疎通確認に使う`Redis`クライアント。

	Returns:
		PINGコマンドへの応答が真値であれば`True`。

	Raises:
		redis.exceptions.RedisError: 接続に失敗した場合。
	"""
	return bool(await client.ping())

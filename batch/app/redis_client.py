from typing import cast

from redis.asyncio import Redis, from_url

from app.core.config import BatchSettings

_shared_client: Redis | None = None


def create_redis_client(settings: BatchSettings) -> Redis:
	return cast(Redis, from_url(settings.redis_url, decode_responses=True))  # type: ignore[no-untyped-call]


def get_redis_client(settings: BatchSettings) -> Redis:
	global _shared_client
	if _shared_client is None:
		_shared_client = create_redis_client(settings)
	return _shared_client


async def close_redis_client(client: Redis | None = None) -> None:
	global _shared_client
	client = client or _shared_client
	if client is not None:
		await client.aclose()
	_shared_client = None


async def ping_redis(client: Redis) -> bool:
	return bool(await client.ping())

from typing import cast

from redis.asyncio import Redis, from_url

from app.core.config import BatchSettings


def create_redis_client(settings: BatchSettings) -> Redis:
	return cast(Redis, from_url(settings.redis_url, decode_responses=True))  # type: ignore[no-untyped-call]


async def close_redis_client(client: Redis) -> None:
	await client.aclose()


async def ping_redis(client: Redis) -> bool:
	return bool(await client.ping())

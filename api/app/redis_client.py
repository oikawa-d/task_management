from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_backend_settings


@lru_cache
def get_redis_client() -> Redis:
	settings = get_backend_settings()
	client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
	return client


async def close_redis_client() -> None:
	await get_redis_client().aclose()


async def ping_redis(client: Redis | None = None) -> bool:
	redis_client = client or get_redis_client()
	return bool(await redis_client.ping())

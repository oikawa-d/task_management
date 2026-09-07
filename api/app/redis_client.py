from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_backend_settings


@lru_cache
def get_redis_client() -> Redis:
	settings = get_backend_settings()
	client: Redis = Redis.from_url(settings.redis_url)
	return client

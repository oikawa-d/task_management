import asyncio
import time

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import BackendSettings
from app.schemas.health import ComponentHealth, HealthResponse


async def _check_database(db_engine: AsyncEngine, timeout_seconds: float) -> ComponentHealth:
	started_at = time.monotonic()
	try:
		async with db_engine.connect() as connection:
			await asyncio.wait_for(connection.execute(text("SELECT 1")), timeout=timeout_seconds)
		latency_ms = int((time.monotonic() - started_at) * 1000)
		return ComponentHealth(status="ok", latency_ms=latency_ms)
	except Exception:
		return ComponentHealth(status="error", latency_ms=None)


async def _check_redis(redis_client: Redis, timeout_seconds: float) -> ComponentHealth:
	started_at = time.monotonic()
	try:
		await asyncio.wait_for(redis_client.ping(), timeout=timeout_seconds)
		latency_ms = int((time.monotonic() - started_at) * 1000)
		return ComponentHealth(status="ok", latency_ms=latency_ms)
	except Exception:
		return ComponentHealth(status="error", latency_ms=None)


async def check_health(
	db_engine: AsyncEngine, redis_client: Redis, settings: BackendSettings
) -> tuple[HealthResponse, bool]:
	database_health, redis_health = await asyncio.gather(
		_check_database(db_engine, settings.health_check_timeout_seconds),
		_check_redis(redis_client, settings.health_check_timeout_seconds),
	)
	is_healthy = database_health.status == "ok" and redis_health.status == "ok"
	response = HealthResponse(
		status="ok" if is_healthy else "degraded",
		auth_mode=settings.auth_mode,
		components={"database": database_health, "redis": redis_health},
	)
	return response, is_healthy

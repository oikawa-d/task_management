"""ヘルスチェック用サービス。

DB・Redisへの疎通確認を行い、監視・死活監視エンドポイントの応答を組み立てる。
権限チェックや業務例外は扱わず、接続失敗は例外を送出せず`error`ステータスとして返す。
"""

import asyncio
import time

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import BackendSettings
from app.schemas.health import ComponentHealth, HealthResponse


async def _check_database(db_engine: AsyncEngine, timeout_seconds: float) -> ComponentHealth:
	"""DBへ`SELECT 1`を発行し、疎通と応答時間を確認する。

	接続・実行のいずれで失敗した場合も例外を送出せず、`error`ステータスの
	`ComponentHealth`として結果に反映する。

	Args:
		db_engine: 疎通確認に使用する非同期DBエンジン。
		timeout_seconds: 応答待機のタイムアウト秒数。

	Returns:
		ComponentHealth: 疎通結果（`ok`/`error`）と応答時間（ミリ秒）。
	"""
	started_at = time.monotonic()
	try:
		async with db_engine.connect() as connection:
			await asyncio.wait_for(connection.execute(text("SELECT 1")), timeout=timeout_seconds)
		latency_ms = int((time.monotonic() - started_at) * 1000)
		return ComponentHealth(status="ok", latency_ms=latency_ms)
	except Exception:
		return ComponentHealth(status="error", latency_ms=None)


async def _check_redis(redis_client: Redis, timeout_seconds: float) -> ComponentHealth:
	"""Redisへ`PING`を送信し、疎通と応答時間を確認する。

	接続・実行のいずれで失敗した場合も例外を送出せず、`error`ステータスの
	`ComponentHealth`として結果に反映する。

	Args:
		redis_client: 疎通確認に使用する非同期Redisクライアント。
		timeout_seconds: 応答待機のタイムアウト秒数。

	Returns:
		ComponentHealth: 疎通結果（`ok`/`error`）と応答時間（ミリ秒）。
	"""
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
	"""DBとRedisの疎通確認を並行実行し、システム全体の健全性を判定する。

	両コンポーネントが`ok`の場合のみ全体を健全（`ok`）とし、いずれかが
	失敗した場合は`degraded`として扱う。呼び出し元（ヘルスチェックエンドポイント）は
	返り値の真偽値によってHTTPステータスを切り替える。

	Args:
		db_engine: DB疎通確認に使用する非同期DBエンジン。
		redis_client: Redis疎通確認に使用する非同期クライアント。
		settings: タイムアウト秒数・認証モードを含むバックエンド設定。

	Returns:
		tuple[HealthResponse, bool]: レスポンス本体と、全体が健全かどうかの真偽値。
	"""
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

import asyncio

from app.core.config import get_backend_settings
from app.schemas.health import ComponentHealth
from app.service import health_service


async def test_check_health_all_ok(monkeypatch):
	async def fake_db(engine, timeout):
		return ComponentHealth(status="ok", latency_ms=1)

	async def fake_redis(client, timeout):
		return ComponentHealth(status="ok", latency_ms=1)

	monkeypatch.setattr(health_service, "_check_database", fake_db)
	monkeypatch.setattr(health_service, "_check_redis", fake_redis)

	response, is_healthy = await health_service.check_health(object(), object(), get_backend_settings())

	assert is_healthy is True
	assert response.status == "ok"
	assert response.components["database"].status == "ok"
	assert response.components["redis"].status == "ok"


async def test_check_health_database_error(monkeypatch):
	async def fake_db(engine, timeout):
		return ComponentHealth(status="error", latency_ms=None)

	async def fake_redis(client, timeout):
		return ComponentHealth(status="ok", latency_ms=1)

	monkeypatch.setattr(health_service, "_check_database", fake_db)
	monkeypatch.setattr(health_service, "_check_redis", fake_redis)

	response, is_healthy = await health_service.check_health(object(), object(), get_backend_settings())

	assert is_healthy is False
	assert response.status == "degraded"
	assert response.components["database"].status == "error"
	assert response.components["database"].latency_ms is None


async def test_check_health_redis_error(monkeypatch):
	async def fake_db(engine, timeout):
		return ComponentHealth(status="ok", latency_ms=1)

	async def fake_redis(client, timeout):
		return ComponentHealth(status="error", latency_ms=None)

	monkeypatch.setattr(health_service, "_check_database", fake_db)
	monkeypatch.setattr(health_service, "_check_redis", fake_redis)

	response, is_healthy = await health_service.check_health(object(), object(), get_backend_settings())

	assert is_healthy is False
	assert response.status == "degraded"
	assert response.components["redis"].status == "error"


async def test_check_database_timeout_treated_as_error():
	class _SlowConnection:
		async def execute(self, statement):
			await asyncio.sleep(0.05)

	class _ConnectContext:
		async def __aenter__(self):
			return _SlowConnection()

		async def __aexit__(self, exc_type, exc, tb):
			return None

	class _Engine:
		def connect(self):
			return _ConnectContext()

	result = await health_service._check_database(_Engine(), timeout_seconds=0.01)

	assert result.status == "error"
	assert result.latency_ms is None


async def test_health_response_excludes_secrets(monkeypatch):
	settings = get_backend_settings()

	async def fake_db(engine, timeout):
		return ComponentHealth(status="error", latency_ms=None)

	async def fake_redis(client, timeout):
		return ComponentHealth(status="ok", latency_ms=1)

	monkeypatch.setattr(health_service, "_check_database", fake_db)
	monkeypatch.setattr(health_service, "_check_redis", fake_redis)

	response, _ = await health_service.check_health(object(), object(), settings)
	body = response.model_dump_json()

	assert settings.database_url not in body
	assert settings.jwt_secret_key not in body

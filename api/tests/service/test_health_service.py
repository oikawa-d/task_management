"""health_service.check_health / _check_database の単体テスト。

DBとRedisの死活確認結果を組み合わせたときの総合ステータス判定、
タイムアウト時のエラー扱い、レスポンスへの機密情報混入がないことを検証する。
"""

import asyncio

from app.core.config import get_backend_settings
from app.schemas.health import ComponentHealth
from app.service import health_service


async def test_check_health_all_ok(monkeypatch):
	"""DBとRedisの両方が正常応答する場合に、全体ステータスが"ok"かつis_healthy=Trueとなることを検証する。"""

	async def fake_db(engine, timeout):
		"""DB疎通チェックを常に正常応答("ok", latency_ms=1)として差し替えるスタブ。"""
		return ComponentHealth(status="ok", latency_ms=1)

	async def fake_redis(client, timeout):
		"""Redis疎通チェックを常に正常応答("ok", latency_ms=1)として差し替えるスタブ。"""
		return ComponentHealth(status="ok", latency_ms=1)

	monkeypatch.setattr(health_service, "_check_database", fake_db)
	monkeypatch.setattr(health_service, "_check_redis", fake_redis)

	response, is_healthy = await health_service.check_health(object(), object(), get_backend_settings())

	assert is_healthy is True
	assert response.status == "ok"
	assert response.components["database"].status == "ok"
	assert response.components["redis"].status == "ok"


async def test_check_health_database_error(monkeypatch):
	"""DBのみ異常応答の場合に、全体ステータスが"degraded"となりis_healthyがFalseになることを検証する。"""

	async def fake_db(engine, timeout):
		"""DB疎通チェックを常にエラー応答("error", latency_ms=None)として差し替えるスタブ。"""
		return ComponentHealth(status="error", latency_ms=None)

	async def fake_redis(client, timeout):
		"""Redis疎通チェックを常に正常応答("ok", latency_ms=1)として差し替えるスタブ。"""
		return ComponentHealth(status="ok", latency_ms=1)

	monkeypatch.setattr(health_service, "_check_database", fake_db)
	monkeypatch.setattr(health_service, "_check_redis", fake_redis)

	response, is_healthy = await health_service.check_health(object(), object(), get_backend_settings())

	assert is_healthy is False
	assert response.status == "degraded"
	assert response.components["database"].status == "error"
	assert response.components["database"].latency_ms is None


async def test_check_health_redis_error(monkeypatch):
	"""Redisのみ異常応答の場合に、全体ステータスが"degraded"となりis_healthyがFalseになることを検証する。"""

	async def fake_db(engine, timeout):
		"""DB疎通チェックを常に正常応答("ok", latency_ms=1)として差し替えるスタブ。"""
		return ComponentHealth(status="ok", latency_ms=1)

	async def fake_redis(client, timeout):
		"""Redis疎通チェックを常にエラー応答("error", latency_ms=None)として差し替えるスタブ。"""
		return ComponentHealth(status="error", latency_ms=None)

	monkeypatch.setattr(health_service, "_check_database", fake_db)
	monkeypatch.setattr(health_service, "_check_redis", fake_redis)

	response, is_healthy = await health_service.check_health(object(), object(), get_backend_settings())

	assert is_healthy is False
	assert response.status == "degraded"
	assert response.components["redis"].status == "error"


async def test_check_database_timeout_treated_as_error():
	"""接続後のクエリ実行がタイムアウト秒数より遅い場合に、_check_databaseが
	タイムアウトをエラー扱い(status="error", latency_ms=None)にすることを検証する。
	"""

	class _SlowConnection:
		"""execute呼び出しにタイムアウトより長い遅延を挟むダミー接続。"""

		async def execute(self, statement):
			"""クエリ実行を模して0.05秒スリープするだけの処理。"""
			await asyncio.sleep(0.05)

	class _ConnectContext:
		"""_SlowConnectionを返す非同期コンテキストマネージャのダミー実装。"""

		async def __aenter__(self):
			"""コンテキスト開始時に_SlowConnectionインスタンスを返す。"""
			return _SlowConnection()

		async def __aexit__(self, exc_type, exc, tb):
			"""例外を抑制せずコンテキストを終了する。"""
			return None

	class _Engine:
		"""connect()が_ConnectContextを返すダミーDBエンジン。"""

		def connect(self):
			"""_ConnectContextを返し、遅い接続を模擬する。"""
			return _ConnectContext()

	result = await health_service._check_database(_Engine(), timeout_seconds=0.01)

	assert result.status == "error"
	assert result.latency_ms is None


async def test_health_response_excludes_secrets(monkeypatch):
	"""DB異常時のヘルスレスポンスJSONに、database_urlやjwt_secret_keyなどの機密情報が含まれないことを検証する。"""
	settings = get_backend_settings()

	async def fake_db(engine, timeout):
		"""DB疎通チェックを常にエラー応答("error", latency_ms=None)として差し替えるスタブ。"""
		return ComponentHealth(status="error", latency_ms=None)

	async def fake_redis(client, timeout):
		"""Redis疎通チェックを常に正常応答("ok", latency_ms=1)として差し替えるスタブ。"""
		return ComponentHealth(status="ok", latency_ms=1)

	monkeypatch.setattr(health_service, "_check_database", fake_db)
	monkeypatch.setattr(health_service, "_check_redis", fake_redis)

	response, _ = await health_service.check_health(object(), object(), settings)
	body = response.model_dump_json()

	assert settings.database_url not in body
	assert settings.jwt_secret_key not in body

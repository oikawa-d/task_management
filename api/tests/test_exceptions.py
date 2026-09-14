from app.core.exceptions import (
	ForbiddenError,
	NotFoundError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	register_error_handling,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


class _Payload(BaseModel):
	name: str


def _build_app() -> FastAPI:
	app = FastAPI()
	register_error_handling(app)

	@app.get("/boom-app-error")
	async def boom_app_error() -> None:
		raise NotFoundError()

	@app.get("/boom-forbidden")
	async def boom_forbidden() -> None:
		raise ForbiddenError(message="権限がありません", details={"reason": "role"})

	@app.get("/boom-rate-limit")
	async def boom_rate_limit() -> None:
		raise TooManyAttemptsError(retry_after=42)

	@app.get("/boom-unhandled")
	async def boom_unhandled() -> None:
		raise RuntimeError("unexpected")

	@app.get("/boom-service-unavailable")
	async def boom_service_unavailable() -> None:
		raise ServiceUnavailableError()

	@app.get("/boom-redis-error")
	async def boom_redis_error() -> None:
		raise RedisConnectionError("redis down")

	@app.get("/boom-operational-error")
	async def boom_operational_error() -> None:
		raise OperationalError("SELECT 1", {}, Exception("connection refused"))

	@app.get("/boom-interface-error")
	async def boom_interface_error() -> None:
		raise InterfaceError("SELECT 1", {}, Exception("connection lost"))

	@app.get("/boom-pool-timeout-error")
	async def boom_pool_timeout_error() -> None:
		raise SQLAlchemyTimeoutError("接続プールの取得がタイムアウトしました")

	@app.post("/validate")
	async def validate(payload: _Payload) -> dict[str, str]:
		return {"name": payload.name}

	@app.get("/ok")
	async def ok() -> dict[str, bool]:
		return {"ok": True}

	return app


def _client() -> TestClient:
	return TestClient(_build_app(), raise_server_exceptions=False)


def test_app_error_converted_to_common_error_response() -> None:
	res = _client().get("/boom-app-error")

	assert res.status_code == 404
	body = res.json()
	assert body["error"]["code"] == "NOT_FOUND"
	assert "request_id" in body["error"]


def test_app_error_with_details() -> None:
	res = _client().get("/boom-forbidden")

	assert res.status_code == 403
	body = res.json()
	assert body["error"]["code"] == "FORBIDDEN"
	assert body["error"]["details"] == {"reason": "role"}


def test_rate_limit_error_includes_retry_after_header() -> None:
	res = _client().get("/boom-rate-limit")

	assert res.status_code == 429
	assert res.headers["Retry-After"] == "42"


def test_unhandled_exception_converted_to_internal_error() -> None:
	res = _client().get("/boom-unhandled")

	assert res.status_code == 500
	body = res.json()
	assert body["error"]["code"] == "INTERNAL_ERROR"
	assert body["error"]["message"] == "サーバーエラーが発生しました"


def _assert_service_unavailable_body(body: dict) -> None:
	assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
	assert body["error"]["message"] == "現在サービスをご利用いただけません"
	assert body["error"]["details"] is None
	assert "request_id" in body["error"]


def test_service_unavailable_app_error_returns_503() -> None:
	res = _client().get("/boom-service-unavailable")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_redis_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-redis-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_operational_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-operational-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_interface_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-interface-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_pool_timeout_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-pool-timeout-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_validation_error_returns_field_details() -> None:
	res = _client().post("/validate", json={})

	assert res.status_code == 422
	body = res.json()
	assert body["error"]["code"] == "VALIDATION_ERROR"
	assert body["error"]["details"][0]["field"].endswith("name")


def test_response_includes_request_id_header() -> None:
	res = _client().get("/ok")

	assert res.status_code == 200
	assert "X-Request-ID" in res.headers

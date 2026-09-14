import logging
from types import SimpleNamespace
from unittest.mock import patch

import app.core.exceptions as exceptions_module
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
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError
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
		raise OperationalError("SELECT 1", {}, SimpleNamespace(sqlstate="08006"))

	@app.get("/boom-unknown-operational-error")
	async def boom_unknown_operational_error() -> None:
		raise OperationalError("SELECT 1", {}, SimpleNamespace(sqlstate="40P01"))

	@app.get("/boom-interface-error")
	async def boom_interface_error() -> None:
		raise InterfaceError("SELECT 1", {}, Exception("connection lost"))

	@app.get("/boom-pool-timeout-error")
	async def boom_pool_timeout_error() -> None:
		raise SQLAlchemyTimeoutError("接続プールの取得がタイムアウトしました")

	@app.get("/boom-disconnection-error")
	async def boom_disconnection_error() -> None:
		raise DisconnectionError("connection invalidated")

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


def test_503_handlers_emit_common_structured_log_fields() -> None:
	with patch.object(exceptions_module.logger, "exception") as log_exception:
		app_error_response = _client().get("/boom-service-unavailable")
		infra_error_response = _client().get("/boom-redis-error")

	assert log_exception.call_count == 2
	app_extra = log_exception.call_args_list[0].kwargs["extra"]
	infra_extra = log_exception.call_args_list[1].kwargs["extra"]

	assert app_extra == {
		"event": "service_unavailable",
		"request_id": app_error_response.json()["error"]["request_id"],
	}
	assert infra_extra == {
		"event": "service_unavailable",
		"request_id": infra_error_response.json()["error"]["request_id"],
	}


def test_app_error_handler_does_not_log_client_errors(caplog) -> None:
	with caplog.at_level(logging.ERROR, logger="app.error"):
		response = _client().get("/boom-app-error")

	assert response.status_code == 404
	assert not [record for record in caplog.records if record.name == "app.error"]


def test_redis_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-redis-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_operational_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-operational-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_operational_error_with_unmapped_sqlstate_returns_internal_error() -> None:
	res = _client().get("/boom-unknown-operational-error")

	assert res.status_code == 500
	assert res.json()["error"]["code"] == "INTERNAL_ERROR"


def test_interface_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-interface-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_pool_timeout_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-pool-timeout-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_disconnection_error_is_converted_to_503_by_infra_error_handler() -> None:
	res = _client().get("/boom-disconnection-error")

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

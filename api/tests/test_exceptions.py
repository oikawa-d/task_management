from app.core.exceptions import ForbiddenError, NotFoundError, TooManyAttemptsError, register_error_handling
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


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

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from app.core import history_middleware
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx2 import ASGITransport, AsyncClient


def _settings() -> MagicMock:
	return MagicMock(
		api_history_body_max_bytes=4096,
		api_history_error_detail_max_length=100,
		trusted_proxy_cidrs=[],
	)


@pytest.mark.asyncio
async def test_api_request_is_recorded_with_redacted_body_and_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
	app = FastAPI()
	history_middleware.register_history_middleware(app)

	@app.post("/api/test")
	async def test_route() -> JSONResponse:
		return JSONResponse({"ok": True})

	settings = _settings()
	save_history = AsyncMock()
	monkeypatch.setattr(history_middleware, "get_backend_settings", lambda: settings)
	monkeypatch.setattr(history_middleware, "_save_history", save_history)

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
		response = await client.post(
			"/api/test",
			json={
				"password": "secret",
				"current_password": "old",
				"new_password": "new",
				"password_confirm": "new",
				"nested": {"access_token": "jwt", "visible": "ok"},
			},
		)

	assert response.status_code == 200
	request_id = response.headers["x-request-id"]
	assert UUID(request_id)
	data = save_history.await_args.args[0]
	assert data.request_id == UUID(request_id)
	assert data.path == "/api/test"
	assert data.status == "success"
	assert data.body == {
		"password": "[REDACTED]",
		"current_password": "[REDACTED]",
		"new_password": "[REDACTED]",
		"password_confirm": "[REDACTED]",
		"nested": {"access_token": "[REDACTED]", "visible": "ok"},
	}


@pytest.mark.asyncio
async def test_error_response_is_recorded_with_error_contract(monkeypatch: pytest.MonkeyPatch) -> None:
	app = FastAPI()
	history_middleware.register_history_middleware(app)

	@app.get("/api/test")
	async def test_route() -> JSONResponse:
		return JSONResponse({"error": {"code": "TASK_CONFLICT", "message": "競合"}}, status_code=409)

	settings = _settings()
	save_history = AsyncMock()
	monkeypatch.setattr(history_middleware, "get_backend_settings", lambda: settings)
	monkeypatch.setattr(history_middleware, "_save_history", save_history)

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
		response = await client.get("/api/test")

	assert response.status_code == 409
	data = save_history.await_args.args[0]
	assert data.error_code == "TASK_CONFLICT"
	assert data.error_detail == "競合"


@pytest.mark.asyncio
async def test_history_insert_failure_does_not_change_api_response(monkeypatch: pytest.MonkeyPatch) -> None:
	app = FastAPI()
	history_middleware.register_history_middleware(app)

	@app.get("/api/test")
	async def test_route() -> JSONResponse:
		return JSONResponse({"ok": True})

	settings = _settings()
	monkeypatch.setattr(history_middleware, "get_backend_settings", lambda: settings)
	monkeypatch.setattr(
		history_middleware.api_history_repository,
		"create",
		AsyncMock(side_effect=RuntimeError("db down")),
	)

	class Session:
		async def __aenter__(self) -> MagicMock:
			return MagicMock()

		async def __aexit__(self, *_args: object) -> None:
			return None

	monkeypatch.setattr(history_middleware, "get_session_factory", lambda: lambda: Session())

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
		response = await client.get("/api/test")

	assert response.status_code == 200
	assert response.json() == {"ok": True}

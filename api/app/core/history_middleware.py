import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response

from app.core.client_ip import resolve_client_ip
from app.core.config import BackendSettings, get_backend_settings
from app.db import get_session_factory
from app.repository import api_history_repository
from app.repository.api_history_repository import ApiHistoryCreateInput

logger = logging.getLogger("app.history")
_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = frozenset(
	{
		"password",
		"password_confirmation",
		"current_password",
		"new_password",
		"password_confirm",
		"token",
		"access_token",
		"refresh_token",
		"client_secret",
		"code",
		"state",
		"csrf_token",
	}
)


def _mask(value: Any) -> Any:
	if isinstance(value, dict):
		return {
			_key: (_REDACTED if _key.lower() in _SENSITIVE_KEYS else _mask(_value)) for _key, _value in value.items()
		}
	if isinstance(value, list):
		return [_mask(item) for item in value]
	return value


def _safe_body(request: Request, raw_body: bytes, settings: BackendSettings) -> dict[str, object] | None:
	if not raw_body or "application/json" not in request.headers.get("content-type", "").lower():
		return None
	if len(raw_body) > settings.api_history_body_max_bytes:
		return None
	try:
		decoded = json.loads(raw_body)
	except UnicodeError:
		return None
	except json.JSONDecodeError:
		return None
	return _mask(decoded) if isinstance(decoded, dict) else None


def _route_path(request: Request) -> str:
	route = request.scope.get("route")
	path = getattr(route, "path", None)
	return path if isinstance(path, str) else request.url.path


async def _read_response_body(response: Response) -> bytes | None:
	body = getattr(response, "body", None)
	if isinstance(body, bytes):
		return body
	iterator = getattr(response, "body_iterator", None)
	if iterator is None:
		return None
	chunks: list[bytes] = []
	async for chunk in iterator:
		chunks.append(chunk.encode() if isinstance(chunk, str) else chunk)

	async def replay() -> Any:
		for chunk in chunks:
			yield chunk

	setattr(response, "body_iterator", replay())

	return b"".join(chunks)


def _error_fields(response: Response, body: bytes | None) -> tuple[str | None, str | None]:
	if response.status_code < 400 or body is None:
		return None, None
	try:
		decoded = json.loads(body)
	except UnicodeError:
		return None, None
	except json.JSONDecodeError:
		return None, None
	if not isinstance(decoded, dict):
		return None, None
	error = decoded.get("error")
	if not isinstance(error, dict):
		return None, None
	code = error.get("code")
	detail = error.get("message")
	return (code if isinstance(code, str) else None, detail if isinstance(detail, str) else None)


async def _save_history(data: ApiHistoryCreateInput) -> None:
	try:
		async with get_session_factory()() as db:
			await api_history_repository.create(db, data)
			await db.commit()
	except Exception:
		logger.exception(
			"api history save failed",
			extra={"event": "api_history_write_failed", "request_id": str(data.request_id)},
		)


def register_history_middleware(app: FastAPI) -> None:
	@app.middleware("http")
	async def history_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
		if not request.url.path.startswith("/api"):
			return await call_next(request)

		settings = get_backend_settings()
		request_id = uuid.uuid4()
		request.state.request_id = str(request_id)
		started = time.perf_counter()
		raw_body = await request.body()

		async def receive() -> dict[str, Any]:
			return {"type": "http.request", "body": raw_body, "more_body": False}

		request._receive = receive
		response: Response | None = None
		response_body: bytes | None = None
		try:
			response = await call_next(request)
			response_body = await _read_response_body(response)
		finally:
			status_code = response.status_code if response is not None else 500
			error_code, error_detail = (
				_error_fields(response, response_body) if response is not None else ("INTERNAL_ERROR", None)
			)
			if status_code >= 400 and error_code is None and error_detail is None:
				error_code = "HTTP_ERROR"
			client_ip = resolve_client_ip(request, settings.trusted_proxy_cidrs).client_ip
			data = ApiHistoryCreateInput(
				request_id=request_id,
				method=request.method,
				path=_route_path(request),
				status="error" if status_code >= 400 else "success",
				status_code=status_code,
				error_code=error_code,
				error_detail=(error_detail or "")[: settings.api_history_error_detail_max_length] or None,
				body=_safe_body(request, raw_body, settings),
				user_id=getattr(getattr(request.state, "current_user", None), "id", None),
				ip_address=client_ip,
				user_agent=request.headers.get("user-agent"),
				duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
			)
			await _save_history(data)
			if response is not None:
				response.headers.setdefault("X-Request-ID", str(request_id))
			logger.info("api request", extra={"event": "api_request", "request_id": str(request_id)})
		assert response is not None
		return response

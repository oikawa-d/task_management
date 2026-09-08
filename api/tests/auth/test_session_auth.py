from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import BackendSettings
from app.core.exceptions import NotSupportedInModeError
from app.repository.redis_store_common import SessionData
from fastapi import Response
from starlette.requests import Request


def _settings() -> BackendSettings:
	return BackendSettings(
		database_url="postgresql+asyncpg://test:test@localhost/test",
		jwt_secret_key="test-secret",
		google_client_id="client",
		google_client_secret="secret",
		initial_admin_email="admin@example.com",
		initial_admin_username="admin",
		initial_admin_password="Password1!",
		session_ttl_seconds=30,
		session_absolute_ttl_seconds=300,
		cookie_secure=True,
	)


def _request(cookie: str | None = None) -> Request:
	headers = [] if cookie is None else [(b"cookie", cookie.encode())]
	return Request({"type": "http", "headers": headers, "client": ("127.0.0.1", 1234)})


def _user() -> SimpleNamespace:
	return SimpleNamespace(id=uuid4())


@pytest.mark.asyncio
async def test_login_sets_http_only_session_and_readable_csrf_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	monkeypatch.setattr(
		"app.auth.session_auth.redis_store.create_session",
		lambda user_id, ip, ttl: _create_session(user_id, ip, ttl),
	)
	strategy = SessionAuthStrategy(_settings())
	response = Response()

	result = await strategy.login(user, _request(), response)
	cookies = [value.decode() for key, value in response.raw_headers if key == b"set-cookie"]

	assert result.auth_mode == "session"
	assert result.access_token is None
	assert result.refresh_token is None
	assert result.csrf_token == "csrf-token"
	assert result.expires_in == 30
	assert any("cerberus_sid=session-id" in value and "HttpOnly" in value and "Secure" in value for value in cookies)
	assert any("cerberus_csrf=csrf-token" in value and "HttpOnly" not in value for value in cookies)


async def _create_session(user_id: object, ip: str | None, ttl: int) -> tuple[str, str]:
	assert ip == "127.0.0.1"
	assert ttl == 30
	return "session-id", "csrf-token"


@pytest.mark.asyncio
async def test_authenticate_touches_valid_session_and_rejects_expired_session(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	monkeypatch.setattr(
		"app.auth.session_auth.redis_store.get_session",
		lambda session_id: _get_session(session_id, user_id),
	)
	monkeypatch.setattr("app.auth.session_auth.redis_store.touch_session", lambda *args: _touch_session(*args))
	strategy = SessionAuthStrategy(_settings())

	context = await strategy.authenticate(_request("cerberus_sid=session-id"))
	assert context is not None
	assert context.user_id == user_id
	assert context.session_id == "session-id"

	monkeypatch.setattr("app.auth.session_auth.redis_store.touch_session", lambda *args: _false_touch(*args))
	assert await strategy.authenticate(_request("cerberus_sid=session-id")) is None


async def _get_session(session_id: str, user_id: UUID) -> SessionData:
	assert session_id == "session-id"
	return SessionData(user_id, datetime.now(UTC), "127.0.0.1")


async def _touch_session(*args: object) -> bool:
	assert args[0] == "session-id"
	return True


async def _false_touch(*args: object) -> bool:
	return False


@pytest.mark.asyncio
async def test_logout_deletes_session_and_clears_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	monkeypatch.setattr(
		"app.auth.session_auth.redis_store.get_session",
		lambda session_id: _get_session(session_id, user_id),
	)
	monkeypatch.setattr("app.auth.session_auth.redis_store.delete_session", lambda *args: _delete_session(*args))
	strategy = SessionAuthStrategy(_settings())
	response = Response()

	await strategy.logout(_request("cerberus_sid=session-id"), response)

	assert len([header for key, header in response.raw_headers if key == b"set-cookie"]) == 2
	assert all(b"Max-Age=0" in header for key, header in response.raw_headers if key == b"set-cookie")


async def _delete_session(session_id: str, user_id: object) -> None:
	assert session_id == "session-id"


@pytest.mark.asyncio
async def test_refresh_is_not_supported_in_session_mode() -> None:
	with pytest.raises(NotSupportedInModeError):
		await SessionAuthStrategy(_settings()).refresh(_request(), Response())

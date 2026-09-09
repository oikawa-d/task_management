from types import SimpleNamespace

import pytest
from app.api.deps import verify_csrf, verify_origin
from app.core.config import BackendSettings
from app.core.exceptions import CsrfInvalidError, ServiceUnavailableError
from starlette.requests import Request


def _settings(**overrides: object) -> BackendSettings:
	values = {
		"database_url": "postgresql+asyncpg://user:pass@localhost/db",
		"jwt_secret_key": "test-secret",
		"google_client_id": "client",
		"google_client_secret": "secret",
		"initial_admin_email": "admin@example.com",
		"initial_admin_username": "admin",
		"initial_admin_password": "password",
		"cors_allow_origins": ["https://app.example.com"],
	}
	values.update(overrides)
	return BackendSettings(_env_file=None, **values)


def _request(
	method: str = "POST",
	path: str = "/api/projects",
	headers: dict[str, str] | None = None,
	cookies: dict[str, str] | None = None,
	scheme: str = "https",
) -> Request:
	scope = {
		"type": "http",
		"http_version": "1.1",
		"method": method,
		"scheme": scheme,
		"path": path,
		"raw_path": path.encode(),
		"query_string": b"",
		"headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
		"server": ("app.example.com", 443 if scheme == "https" else 80),
		"client": ("127.0.0.1", 1234),
	}
	request = Request(scope)
	if cookies:
		cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
		request_headers = {**(headers or {}), "cookie": cookie_header}
		scope["headers"] = [(key.lower().encode(), value.encode()) for key, value in request_headers.items()]
	return request


@pytest.mark.asyncio
async def test_verify_origin_accepts_exact_allowed_origin() -> None:
	request = _request(headers={"Origin": "https://app.example.com"})

	assert await verify_origin(request, _settings()) is None


@pytest.mark.asyncio
async def test_verify_origin_rejects_disallowed_origin() -> None:
	request = _request(headers={"Origin": "https://evil.example.com"})

	with pytest.raises(CsrfInvalidError):
		await verify_origin(request, _settings())


@pytest.mark.asyncio
async def test_verify_origin_uses_referer_only_when_enabled_on_https() -> None:
	request = _request(headers={"Referer": "https://app.example.com/settings"})

	assert await verify_origin(request, _settings(csrf_trust_referer_on_https=True)) is None


@pytest.mark.asyncio
async def test_verify_origin_rejects_missing_origin_by_default() -> None:
	request = _request(headers={"Referer": "https://app.example.com/settings"})

	with pytest.raises(CsrfInvalidError):
		await verify_origin(request, _settings())


@pytest.mark.asyncio
async def test_verify_origin_skips_oauth_callback_without_origin() -> None:
	request = _request(path="/api/auth/oauth/google/callback")

	assert await verify_origin(request, _settings()) is None


@pytest.mark.asyncio
async def test_verify_csrf_session_requires_cookie_header_and_redis_match() -> None:
	redis = SimpleNamespace(get=lambda key: _async_value('{"token": "csrf-token"}'))
	request = _request(
		cookies={"cerberus_sid": "sid", "cerberus_csrf": "csrf-token"},
		headers={"X-CSRF-Token": "csrf-token"},
	)

	assert await verify_csrf(request, SimpleNamespace(mode="session"), redis, _settings()) is None


@pytest.mark.asyncio
async def test_verify_csrf_rejects_missing_header() -> None:
	redis = SimpleNamespace(get=lambda key: _async_value('{"token": "csrf-token"}'))
	request = _request(cookies={"cerberus_sid": "sid", "cerberus_csrf": "csrf-token"})

	with pytest.raises(CsrfInvalidError):
		await verify_csrf(request, SimpleNamespace(mode="session"), redis, _settings())


@pytest.mark.asyncio
async def test_verify_csrf_returns_service_unavailable_when_redis_fails() -> None:
	from redis.exceptions import ConnectionError

	async def fail_get(key: str) -> str:
		raise ConnectionError()

	request = _request(
		cookies={"cerberus_sid": "sid", "cerberus_csrf": "csrf-token"},
		headers={"X-CSRF-Token": "csrf-token"},
	)

	with pytest.raises(ServiceUnavailableError):
		await verify_csrf(request, SimpleNamespace(mode="session"), SimpleNamespace(get=fail_get), _settings())


@pytest.mark.asyncio
async def test_verify_csrf_jwt_does_not_access_redis() -> None:
	redis = SimpleNamespace(get=lambda key: pytest.fail("JWT CSRF must not read Redis"))
	request = _request(cookies={"cerberus_csrf": "csrf-token"}, headers={"X-CSRF-Token": "csrf-token"})

	assert await verify_csrf(request, SimpleNamespace(mode="jwt"), redis, _settings()) is None


@pytest.mark.asyncio
async def test_verify_csrf_skips_safe_method_and_oauth_callback() -> None:
	get_redis = SimpleNamespace(get=lambda key: pytest.fail("safe request must not read Redis"))

	assert await verify_csrf(_request(method="GET"), SimpleNamespace(mode="session"), get_redis, _settings()) is None
	assert (
		await verify_csrf(
			_request(path="/api/auth/oauth/google/callback"),
			SimpleNamespace(mode="session"),
			get_redis,
			_settings(),
		)
		is None
	)


async def _async_value(value: str) -> str:
	return value

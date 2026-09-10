from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core import security
from app.core.deps import _origin_from_referer, verify_csrf, verify_origin
from app.core.exceptions import CsrfInvalidError
from starlette.requests import Request


def _settings(
	*,
	cors_allow_origins: list[str] | None = None,
	csrf_trust_referer_on_https: bool = False,
	cookie_name_session: str = "cerberus_sid",
	cookie_name_csrf: str = "cerberus_csrf",
) -> SimpleNamespace:
	return SimpleNamespace(
		cors_allow_origins=cors_allow_origins if cors_allow_origins is not None else ["http://localhost:5173"],
		csrf_trust_referer_on_https=csrf_trust_referer_on_https,
		cookie_name_session=cookie_name_session,
		cookie_name_csrf=cookie_name_csrf,
	)


def _strategy(mode: str) -> SimpleNamespace:
	return SimpleNamespace(mode=mode)


def _request(
	*,
	scheme: str = "http",
	headers: dict[str, str] | None = None,
	cookies: dict[str, str] | None = None,
) -> Request:
	raw_headers: list[tuple[bytes, bytes]] = []
	for key, value in (headers or {}).items():
		raw_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
	if cookies:
		cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
		raw_headers.append((b"cookie", cookie_header.encode("latin-1")))
	scope = {
		"type": "http",
		"method": "POST",
		"scheme": scheme,
		"path": "/api/projects",
		"headers": raw_headers,
		"query_string": b"",
		"server": ("testserver", 80),
		"client": ("testclient", 123),
	}
	return Request(scope)


class TestVerifyOrigin:
	async def test_allowed_origin_passes(self) -> None:
		request = _request(headers={"origin": "http://localhost:5173"})

		await verify_origin(request, _settings())

	async def test_disallowed_origin_is_rejected(self) -> None:
		request = _request(headers={"origin": "http://evil.example"})

		with pytest.raises(CsrfInvalidError):
			await verify_origin(request, _settings())

	async def test_missing_origin_is_rejected_by_default(self) -> None:
		request = _request()

		with pytest.raises(CsrfInvalidError):
			await verify_origin(request, _settings())

	async def test_missing_origin_falls_back_to_referer_on_https_when_trusted(self) -> None:
		request = _request(scheme="https", headers={"referer": "https://localhost:5173/dashboard"})
		settings = _settings(cors_allow_origins=["https://localhost:5173"], csrf_trust_referer_on_https=True)

		await verify_origin(request, settings)

	async def test_missing_origin_referer_fallback_rejects_mismatched_referer(self) -> None:
		request = _request(scheme="https", headers={"referer": "https://evil.example/x"})
		settings = _settings(cors_allow_origins=["https://localhost:5173"], csrf_trust_referer_on_https=True)

		with pytest.raises(CsrfInvalidError):
			await verify_origin(request, settings)

	async def test_referer_fallback_not_applied_on_plain_http_even_if_trusted(self) -> None:
		request = _request(scheme="http", headers={"referer": "http://localhost:5173/x"})
		settings = _settings(cors_allow_origins=["http://localhost:5173"], csrf_trust_referer_on_https=True)

		with pytest.raises(CsrfInvalidError):
			await verify_origin(request, settings)

	def test_origin_from_referer_extracts_scheme_and_host(self) -> None:
		assert _origin_from_referer("https://example.com/path?x=1") == "https://example.com"

	def test_origin_from_referer_rejects_malformed_values(self) -> None:
		assert _origin_from_referer("") is None
		assert _origin_from_referer(None) is None
		assert _origin_from_referer("not-a-url") is None


class TestVerifyCsrfSessionMode:
	async def test_matching_cookie_header_and_redis_value_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
		get_csrf_token = AsyncMock(return_value="token-123")
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(headers={"x-csrf-token": "token-123"}, cookies={"cerberus_sid": "sid-1"})

		await verify_csrf(request, _strategy("session"), _settings())

		get_csrf_token.assert_awaited_once_with("sid-1")

	async def test_missing_header_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		get_csrf_token = AsyncMock(return_value="token-123")
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(cookies={"cerberus_sid": "sid-1"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("session"), _settings())
		get_csrf_token.assert_not_awaited()

	async def test_missing_session_cookie_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		get_csrf_token = AsyncMock(return_value="token-123")
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(headers={"x-csrf-token": "token-123"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("session"), _settings())
		get_csrf_token.assert_not_awaited()

	async def test_redis_value_mismatch_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", AsyncMock(return_value="other-token"))
		request = _request(headers={"x-csrf-token": "token-123"}, cookies={"cerberus_sid": "sid-1"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("session"), _settings())

	async def test_missing_redis_value_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", AsyncMock(return_value=None))
		request = _request(headers={"x-csrf-token": "token-123"}, cookies={"cerberus_sid": "sid-1"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("session"), _settings())


class TestVerifyCsrfJwtMode:
	async def test_matching_cookie_and_header_passes_without_redis_access(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		get_csrf_token = AsyncMock()
		monkeypatch.setattr("app.core.deps.redis_store.get_csrf_token", get_csrf_token)
		request = _request(headers={"x-csrf-token": "token-abc"}, cookies={"cerberus_csrf": "token-abc"})

		await verify_csrf(request, _strategy("jwt"), _settings())

		get_csrf_token.assert_not_awaited()

	async def test_cookie_header_mismatch_is_rejected(self) -> None:
		request = _request(headers={"x-csrf-token": "token-abc"}, cookies={"cerberus_csrf": "token-xyz"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("jwt"), _settings())

	async def test_missing_csrf_cookie_is_rejected(self) -> None:
		request = _request(headers={"x-csrf-token": "token-abc"})

		with pytest.raises(CsrfInvalidError):
			await verify_csrf(request, _strategy("jwt"), _settings())


class TestCsrfTokensMatch:
	def test_equal_tokens_match(self) -> None:
		assert security.csrf_tokens_match("same-token", "same-token") is True

	def test_different_tokens_do_not_match(self) -> None:
		assert security.csrf_tokens_match("token-a", "token-b") is False

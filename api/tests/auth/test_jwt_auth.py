from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from app.auth.base import LoginResult
from app.auth.jwt_auth import JwtAuthStrategy
from app.core.config import BackendSettings
from app.core.exceptions import TokenInvalidError, TokenRevokedError
from app.repository.redis_store_common import RefreshData, TokenReused
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
		access_token_ttl_seconds=60,
		refresh_ttl_seconds=900,
		cookie_secure=True,
	)


def _request(headers: list[tuple[bytes, bytes]] | None = None, cookie: str | None = None) -> Request:
	request_headers = headers or []
	if cookie is not None:
		request_headers = [*request_headers, (b"cookie", cookie.encode())]
	return Request({"type": "http", "headers": request_headers})


def _user() -> SimpleNamespace:
	return SimpleNamespace(id=uuid4())


@pytest.mark.asyncio
async def test_login_issues_access_token_and_refresh_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
	stored: dict[str, tuple[object, object, int]] = {}

	async def store(token: str, user_id: object, family_id: str, ttl: int) -> None:
		stored[token] = (user_id, family_id, ttl)

	monkeypatch.setattr("app.auth.jwt_auth.redis_store.store_refresh_token", store)
	strategy = JwtAuthStrategy(_settings())
	response = Response()
	result = await strategy.login(_user(), _request(), response)

	claims = jwt.decode(result.access_token or "", _settings().jwt_secret_key, algorithms=["HS256"])
	cookies = [value.decode() for key, value in response.raw_headers if key == b"set-cookie"]
	assert claims["typ"] == "access"
	assert claims["jti"]
	assert len(stored) == 1
	assert result.refresh_token in stored
	assert any(
		"cerberus_rt=" in value
		and "HttpOnly" in value
		and "SameSite=strict" in value
		and "Path=/api/auth" in value
		and "Max-Age=900" in value
		for value in cookies
	)
	assert any(
		"cerberus_csrf=" in value and "HttpOnly" not in value and "Path=/" in value and "Max-Age=900" in value
		for value in cookies
	)


@pytest.mark.asyncio
async def test_authenticate_accepts_only_valid_access_bearer_token() -> None:
	strategy = JwtAuthStrategy(_settings())
	user_id = uuid4()
	token = jwt.encode(
		{
			"sub": str(user_id),
			"iat": datetime.now(UTC),
			"exp": datetime.now(UTC) + timedelta(minutes=1),
			"jti": "jti",
			"typ": "access",
		},
		_settings().jwt_secret_key,
		algorithm="HS256",
	)

	context = await strategy.authenticate(_request([(b"authorization", f"Bearer {token}".encode())]))
	assert context is not None
	assert context.user_id == user_id

	wrong_type = jwt.encode(
		{
			"sub": str(user_id),
			"iat": datetime.now(UTC),
			"exp": datetime.now(UTC) + timedelta(minutes=1),
			"jti": "jti",
			"typ": "refresh",
		},
		_settings().jwt_secret_key,
		algorithm="HS256",
	)
	assert await strategy.authenticate(_request([(b"authorization", f"Bearer {wrong_type}".encode())])) is None

	expired = jwt.encode(
		{
			"sub": str(user_id),
			"iat": datetime.now(UTC) - timedelta(minutes=2),
			"exp": datetime.now(UTC) - timedelta(minutes=1),
			"jti": "expired-jti",
			"typ": "access",
		},
		_settings().jwt_secret_key,
		algorithm="HS256",
	)
	assert await strategy.authenticate(_request([(b"authorization", f"Bearer {expired}".encode())])) is None

	wrong_signature = jwt.encode(
		{
			"sub": str(user_id),
			"iat": datetime.now(UTC),
			"exp": datetime.now(UTC) + timedelta(minutes=1),
			"jti": "wrong-signature",
			"typ": "access",
		},
		"wrong-secret",
		algorithm="HS256",
	)
	assert await strategy.authenticate(_request([(b"authorization", f"Bearer {wrong_signature}".encode())])) is None


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_reuse_revokes_family(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	metadata = RefreshData(user_id, datetime.now(UTC), "family-1")
	rotated_token: list[str] = []

	async def rotate(*args: object) -> RefreshData:
		rotated_token.append(str(args[1]))
		return metadata

	monkeypatch.setattr("app.auth.jwt_auth.redis_store.rotate_refresh_token", rotate)
	strategy = JwtAuthStrategy(_settings())
	response = Response()
	result = await strategy.refresh(_request(cookie="cerberus_rt=old"), response)
	assert result.auth_mode == "jwt"
	assert result.refresh_token == rotated_token[0]

	monkeypatch.setattr(
		"app.auth.jwt_auth.redis_store.rotate_refresh_token", lambda *args: _reused(*args, metadata=metadata)
	)
	monkeypatch.setattr("app.auth.jwt_auth.redis_store.revoke_token_family", lambda *args: _revoke_family(*args))
	with pytest.raises(TokenRevokedError):
		await strategy.refresh(_request(cookie="cerberus_rt=old"), Response())


async def _reused(*args: object, metadata: RefreshData) -> TokenReused:
	return TokenReused(metadata.user_id, metadata.family_id)


async def _revoke_family(*args: object) -> int:
	return 1


@pytest.mark.asyncio
async def test_refresh_without_cookie_is_invalid_and_logout_clears_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	strategy = JwtAuthStrategy(_settings())
	with pytest.raises(TokenInvalidError):
		await strategy.refresh(_request(), Response())

	monkeypatch.setattr("app.auth.jwt_auth.redis_store.get_refresh_token", lambda token: _missing(token))
	response = Response()
	await strategy.logout(_request(cookie="cerberus_rt=missing"), response)
	assert len([header for key, header in response.raw_headers if key == b"set-cookie"]) == 2


@pytest.mark.asyncio
async def test_rollback_login_revokes_refresh_token_and_clears_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
	revoke = AsyncMock()
	monkeypatch.setattr("app.auth.jwt_auth.redis_store.revoke_refresh_token", revoke)
	strategy = JwtAuthStrategy(_settings())
	response = Response()
	result = LoginResult("jwt", "access-token", "refresh-token", "csrf-token", 60)
	user = _user()
	strategy._set_cookies(response, result.refresh_token or "", result.csrf_token or "")

	await strategy.rollback_login(user, result, response)

	revoke.assert_awaited_once_with(result.refresh_token, user.id)
	deleted = [header for key, header in response.raw_headers if key == b"set-cookie"][2:]
	assert len(deleted) == 2
	assert all(b"Max-Age=0" in header for header in deleted)


@pytest.mark.asyncio
async def test_refresh_with_expired_or_deleted_token_is_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr("app.auth.jwt_auth.redis_store.rotate_refresh_token", lambda *args: _missing(args))
	with pytest.raises(TokenRevokedError):
		await JwtAuthStrategy(_settings()).refresh(_request(cookie="cerberus_rt=expired"), Response())


async def _missing(token: object) -> RefreshData | None:
	return None

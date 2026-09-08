from types import SimpleNamespace
from uuid import uuid4

from app.repository.session_repository import SessionRepository
from app.service.session_auth_service import SessionAuthService
from fastapi import Response
from starlette.requests import Request
from tests.repository.test_session_repository import MemoryRedis


def _settings() -> SimpleNamespace:
	return SimpleNamespace(
		session_ttl_seconds=30,
		session_absolute_ttl_seconds=300,
		cookie_name_session="cerberus_sid",
		cookie_name_csrf="cerberus_csrf",
		cookie_secure=True,
		cookie_samesite="lax",
		cookie_domain="",
	)


def _request(cookie: str) -> Request:
	return Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})


async def test_login_sets_session_and_csrf_cookies_with_design_attributes() -> None:
	service = SessionAuthService(SessionRepository(MemoryRedis()), _settings())
	response = Response()

	result = await service.login(uuid4(), response=response)
	set_cookies = [value.decode() for key, value in response.raw_headers if key == b"set-cookie"]

	assert result.auth_mode == "session"
	assert result.expires_in == 30
	assert any("cerberus_sid=" in value and "HttpOnly" in value and "Secure" in value for value in set_cookies)
	assert any("cerberus_csrf=" in value and "HttpOnly" not in value and "Secure" in value for value in set_cookies)
	assert all("SameSite=lax" in value and "Max-Age" not in value for value in set_cookies)


async def test_authenticate_resolves_login_and_rejects_tampered_cookie() -> None:
	redis = MemoryRedis()
	service = SessionAuthService(SessionRepository(redis), _settings())
	response = Response()
	user_id = uuid4()
	result = await service.login(user_id, response=response)

	context = await service.authenticate(_request(f"cerberus_sid={result.session_id}"))
	assert context is not None
	assert context.user_id == user_id
	assert context.session_id == result.session_id
	assert await service.authenticate(_request("cerberus_sid=modified")) is None


async def test_logout_deletes_session_and_expires_cookies() -> None:
	redis = MemoryRedis()
	service = SessionAuthService(SessionRepository(redis), _settings())
	login_response = Response()
	result = await service.login(uuid4(), response=login_response)
	request = _request(f"cerberus_sid={result.session_id}; cerberus_csrf={result.csrf_token}")
	logout_response = Response()

	await service.logout(request, logout_response)

	assert await service.authenticate(request) is None
	set_cookies = [value.decode() for key, value in logout_response.raw_headers if key == b"set-cookie"]
	assert len(set_cookies) == 2
	assert all("Max-Age=0" in value for value in set_cookies)

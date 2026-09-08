from uuid import uuid4

import pytest
from app.api.deps import get_current_user
from app.core.exceptions import SessionExpiredError, UnauthenticatedError
from app.repository.session_repository import SessionRepository
from app.service.session_auth_service import SessionAuthService
from fastapi import Response
from starlette.requests import Request
from tests.repository.test_session_repository import MemoryRedis
from tests.service.test_session_auth_service import _request, _settings


@pytest.mark.asyncio
async def test_get_current_user_returns_session_context_after_login() -> None:
	service = SessionAuthService(SessionRepository(MemoryRedis()), _settings())
	response = Response()
	result = await service.login(uuid4(), response=response)

	context = await get_current_user(_request(f"cerberus_sid={result.session_id}"), service)

	assert context.session_id == result.session_id


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_cookie() -> None:
	service = SessionAuthService(SessionRepository(MemoryRedis()), _settings())
	request = Request({"type": "http", "headers": []})

	with pytest.raises(UnauthenticatedError):
		await get_current_user(request, service)


@pytest.mark.asyncio
async def test_get_current_user_reports_expired_or_tampered_cookie() -> None:
	service = SessionAuthService(SessionRepository(MemoryRedis()), _settings())
	request = _request("cerberus_sid=expired-or-tampered")

	with pytest.raises(SessionExpiredError):
		await get_current_user(request, service)

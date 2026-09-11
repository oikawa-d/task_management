from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.auth.base import AuthContext
from app.core.config import get_backend_settings
from app.core.deps import (
	get_current_user,
	get_current_user_optional,
	require_admin,
	verify_csrf_for_logout,
)
from app.core.exceptions import ForbiddenError, UnauthenticatedError, UserInactiveError
from app.schemas.auth import CurrentUser


class _Strategy:
	def __init__(self, context: AuthContext | None):
		self.context = context

	async def authenticate(self, request):
		return self.context


def _user(user_id, *, active=True, role="member"):
	return SimpleNamespace(
		id=user_id,
		username="taro",
		role=role,
		is_active=active,
		email_verified_at=datetime.now(UTC),
	)


class _Db:
	pass


@pytest.mark.asyncio
async def test_get_current_user_uses_database_values(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	monkeypatch.setattr(
		"app.core.deps.user_repository.get_by_id", AsyncMock(side_effect=lambda db, value: _user(value, role="admin"))
	)

	result = await get_current_user(None, _Strategy(AuthContext(user_id, role="member", username="old")), _Db())
	assert result == CurrentUser(
		id=user_id,
		username="taro",
		role="admin",
		is_active=True,
		email_verified_at=result.email_verified_at,
	)


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_and_inactive_users(monkeypatch: pytest.MonkeyPatch) -> None:
	user_id = uuid4()
	monkeypatch.setattr("app.core.deps.user_repository.get_by_id", AsyncMock(return_value=None))
	with pytest.raises(UnauthenticatedError):
		await get_current_user(None, _Strategy(AuthContext(user_id)), _Db())

	monkeypatch.setattr(
		"app.core.deps.user_repository.get_by_id", AsyncMock(side_effect=lambda db, value: _user(value, active=False))
	)
	with pytest.raises(UserInactiveError):
		await get_current_user(None, _Strategy(AuthContext(user_id)), _Db())


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_context_and_require_admin_rejects_member() -> None:
	with pytest.raises(UnauthenticatedError):
		await get_current_user(None, _Strategy(None), _Db())

	with pytest.raises(ForbiddenError):
		require_admin(CurrentUser(id=uuid4(), username="taro", role="member", is_active=True, email_verified_at=None))


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_for_unauthenticated_request() -> None:
	assert await get_current_user_optional(None, _Strategy(None), _Db()) is None


class _CsrfRequest:
	def __init__(self, cookies: dict[str, str]) -> None:
		self.cookies = cookies
		self.headers: dict[str, str] = {}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["session", "jwt"])
async def test_verify_csrf_for_logout_skips_without_auth_cookie(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
	verify_mock = AsyncMock()
	monkeypatch.setattr("app.core.deps.verify_csrf", verify_mock)
	settings = get_backend_settings()

	await verify_csrf_for_logout(_CsrfRequest({}), SimpleNamespace(mode=mode), settings)

	verify_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("mode", "cookie_name"),
	[("session", "cookie_name_session"), ("jwt", "cookie_name_refresh")],
)
async def test_verify_csrf_for_logout_validates_with_auth_cookie(
	monkeypatch: pytest.MonkeyPatch, mode: str, cookie_name: str
) -> None:
	verify_mock = AsyncMock()
	monkeypatch.setattr("app.core.deps.verify_csrf", verify_mock)
	settings = get_backend_settings()
	request = _CsrfRequest({getattr(settings, cookie_name): "value"})

	await verify_csrf_for_logout(request, SimpleNamespace(mode=mode), settings)

	verify_mock.assert_awaited_once()

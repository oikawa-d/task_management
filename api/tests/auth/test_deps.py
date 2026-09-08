from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.auth.base import AuthContext
from app.core.deps import get_current_user, get_current_user_optional, require_admin
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

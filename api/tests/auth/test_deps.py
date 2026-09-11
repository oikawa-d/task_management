from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.auth.base import AuthContext
from app.core.config import get_backend_settings
from app.core.deps import (
	enforce_rate_limit,
	get_current_user,
	get_current_user_optional,
	require_admin,
	verify_csrf_for_logout,
)
from app.core.exceptions import (
	ForbiddenError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	UnauthenticatedError,
	UserInactiveError,
)
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
		self.client = SimpleNamespace(host="127.0.0.1")


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


@pytest.mark.asyncio
async def test_enforce_rate_limit_allows_request_within_limit(monkeypatch: pytest.MonkeyPatch) -> None:
	check_mock = AsyncMock(return_value=1)
	monkeypatch.setattr("app.core.deps.redis_store.check_rate_limit", check_mock)
	settings = get_backend_settings()
	dependency = enforce_rate_limit(
		"register", "rate_limit_register_max_requests", "rate_limit_register_window_seconds"
	)

	await dependency(_CsrfRequest({}), settings)

	assert check_mock.await_args.args == (
		"register",
		"127.0.0.1",
		settings.rate_limit_register_max_requests,
		settings.rate_limit_register_window_seconds,
	)


@pytest.mark.asyncio
async def test_enforce_rate_limit_rejects_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = get_backend_settings()
	monkeypatch.setattr(
		"app.core.deps.redis_store.check_rate_limit",
		AsyncMock(return_value=settings.rate_limit_register_max_requests + 1),
	)
	dependency = enforce_rate_limit(
		"register", "rate_limit_register_max_requests", "rate_limit_register_window_seconds"
	)

	with pytest.raises(TooManyAttemptsError):
		await dependency(_CsrfRequest({}), settings)


@pytest.mark.asyncio
async def test_enforce_rate_limit_fails_closed_on_redis_error(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr("app.core.deps.redis_store.check_rate_limit", AsyncMock(side_effect=RuntimeError("redis down")))
	dependency = enforce_rate_limit(
		"register", "rate_limit_register_max_requests", "rate_limit_register_window_seconds"
	)

	with pytest.raises(ServiceUnavailableError):
		await dependency(_CsrfRequest({}), get_backend_settings())

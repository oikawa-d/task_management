from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api import deps
from app.core.exceptions import ForbiddenError, UnauthenticatedError
from app.service.auth_strategy import AuthContext
from starlette.requests import Request


def _request() -> Request:
	return Request({"type": "http", "method": "GET", "path": "/api/auth/me", "headers": [], "query_string": b""})


class StubStrategy:
	def __init__(self, context: AuthContext | None) -> None:
		self.context = context

	async def authenticate(self, request: Request) -> AuthContext | None:
		return self.context


def _user(*, role: str = "member", is_active: bool = True) -> SimpleNamespace:
	return SimpleNamespace(
		id=uuid4(),
		username="current-user",
		role=role,
		is_active=is_active,
		email_verified_at=datetime.now(timezone.utc),
	)


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_authentication() -> None:
	with pytest.raises(UnauthenticatedError) as error:
		await deps.get_current_user(_request(), StubStrategy(None), None)  # type: ignore[arg-type]

	assert error.value.code == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_get_current_user_rejects_user_missing_from_database(monkeypatch: pytest.MonkeyPatch) -> None:
	async def get_user(db: object, user_id: object) -> None:
		return None

	monkeypatch.setattr(deps.user_repository, "get_by_id", get_user)
	context = AuthContext(user_id=uuid4())

	with pytest.raises(UnauthenticatedError):
		await deps.get_current_user(_request(), StubStrategy(context), None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_current_user_rejects_inactive_user(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user(is_active=False)

	async def get_user(db: object, user_id: object) -> SimpleNamespace:
		return user

	monkeypatch.setattr(deps.user_repository, "get_by_id", get_user)

	with pytest.raises(deps.UserInactiveError) as error:
		await deps.get_current_user(_request(), StubStrategy(AuthContext(user.id)), None)  # type: ignore[arg-type]

	assert error.value.code == "USER_INACTIVE"


@pytest.mark.asyncio
async def test_get_current_user_uses_current_database_user_values(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user(role="admin")

	async def get_user(db: object, user_id: object) -> SimpleNamespace:
		return user

	monkeypatch.setattr(deps.user_repository, "get_by_id", get_user)
	current_user = await deps.get_current_user(
		_request(),
		StubStrategy(AuthContext(user.id, role="member", username="stale-user")),
		None,  # type: ignore[arg-type]
	)

	assert current_user.id == user.id
	assert current_user.username == "current-user"
	assert current_user.role == "admin"


def test_require_admin_rejects_member() -> None:
	user = _user(role="member")
	current_user = deps.CurrentUser(
		id=user.id,
		username=user.username,
		role=user.role,
		is_active=True,
		email_verified_at=None,
	)

	with pytest.raises(ForbiddenError) as error:
		deps.require_admin(current_user)

	assert error.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_when_unauthenticated() -> None:
	result = await deps.get_current_user_optional(_request(), StubStrategy(None), None)  # type: ignore[arg-type]

	assert result is None

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.api.deps import require_admin, require_project_member, require_project_owner
from app.core.exceptions import ForbiddenError, NotFoundError
from app.service.authorization_service import CurrentUser


def _user(*, role: str = "member") -> CurrentUser:
	return CurrentUser(id=uuid.uuid4(), username="user", role=role, is_active=True)


@pytest.mark.asyncio
async def test_require_project_member_returns_404_for_non_member(monkeypatch: pytest.MonkeyPatch) -> None:
	project = SimpleNamespace(id=uuid.uuid4(), owner_id=uuid.uuid4(), is_active=True)
	project_repository = SimpleNamespace(get_by_id=AsyncMock(return_value=project))
	member_repository = SimpleNamespace(exists=AsyncMock(return_value=False))
	monkeypatch.setattr("app.api.deps.project_repository", project_repository)
	monkeypatch.setattr("app.api.deps.project_member_repository", member_repository)
	user = _user()

	with pytest.raises(NotFoundError):
		await require_project_member(project.id, user=user, db=object())
	project_repository.get_by_id.assert_awaited_once()
	member_repository.exists.assert_awaited_once()


@pytest.mark.asyncio
async def test_require_project_owner_returns_403_after_membership_is_confirmed() -> None:
	project = SimpleNamespace(id=uuid.uuid4(), owner_id=uuid.uuid4(), is_active=True)
	user = _user()

	with pytest.raises(ForbiddenError):
		await require_project_owner(project=project, user=user)


def test_require_admin_rejects_member() -> None:
	with pytest.raises(ForbiddenError):
		require_admin(_user())


def test_require_admin_allows_admin() -> None:
	user = _user(role="admin")

	assert require_admin(user) is user

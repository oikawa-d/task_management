import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.deps import require_admin, require_project_member, require_project_owner
from app.core.exceptions import ForbiddenError, NotFoundError
from app.schemas.auth import CurrentUser


def _user(*, role: str = "member") -> CurrentUser:
	return CurrentUser(id=uuid.uuid4(), username="taro", role=role, is_active=True, email_verified_at=None)


def _project(owner_id: uuid.UUID) -> SimpleNamespace:
	return SimpleNamespace(id=uuid.uuid4(), owner_id=owner_id, is_active=True)


class _Db:
	pass


async def test_require_project_member_returns_404_when_project_missing(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr("app.core.deps.project_repository.get_by_id", AsyncMock(return_value=None))
	is_member_mock = AsyncMock(return_value=True)
	monkeypatch.setattr("app.core.deps.project_repository.is_member", is_member_mock)

	with pytest.raises(NotFoundError):
		await require_project_member(uuid.uuid4(), user=_user(), db=_Db())
	is_member_mock.assert_not_awaited()


async def test_require_project_member_returns_404_for_non_member(monkeypatch: pytest.MonkeyPatch) -> None:
	project = _project(uuid.uuid4())
	monkeypatch.setattr("app.core.deps.project_repository.get_by_id", AsyncMock(return_value=project))
	monkeypatch.setattr("app.core.deps.project_repository.is_member", AsyncMock(return_value=False))

	with pytest.raises(NotFoundError):
		await require_project_member(project.id, user=_user(), db=_Db())


async def test_require_project_member_returns_project_for_member(monkeypatch: pytest.MonkeyPatch) -> None:
	project = _project(uuid.uuid4())
	monkeypatch.setattr("app.core.deps.project_repository.get_by_id", AsyncMock(return_value=project))
	monkeypatch.setattr("app.core.deps.project_repository.is_member", AsyncMock(return_value=True))

	result = await require_project_member(project.id, user=_user(), db=_Db())
	assert result is project


async def test_require_project_member_calls_is_member_even_for_admin(monkeypatch: pytest.MonkeyPatch) -> None:
	"""admin bypassはfn_is_project_member側の戻り値に含まれるため、Python側でroleによる分岐を行わない。"""
	project = _project(uuid.uuid4())
	monkeypatch.setattr("app.core.deps.project_repository.get_by_id", AsyncMock(return_value=project))
	is_member_mock = AsyncMock(return_value=True)
	monkeypatch.setattr("app.core.deps.project_repository.is_member", is_member_mock)

	result = await require_project_member(project.id, user=_user(role="admin"), db=_Db())

	assert result is project
	is_member_mock.assert_awaited_once()


async def test_require_project_owner_allows_owner() -> None:
	owner = _user()
	project = _project(owner.id)

	assert await require_project_owner(project=project, user=owner) is project


async def test_require_project_owner_allows_admin_for_non_owned_project() -> None:
	admin = _user(role="admin")
	project = _project(uuid.uuid4())

	assert await require_project_owner(project=project, user=admin) is project


async def test_require_project_owner_rejects_non_owner_member() -> None:
	project = _project(uuid.uuid4())

	with pytest.raises(ForbiddenError):
		await require_project_owner(project=project, user=_user())


def test_require_admin_rejects_member() -> None:
	with pytest.raises(ForbiddenError):
		require_admin(_user())


def test_require_admin_allows_admin() -> None:
	admin = _user(role="admin")
	assert require_admin(admin) is admin

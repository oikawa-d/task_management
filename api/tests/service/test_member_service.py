from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import (
	AlreadyMemberError,
	NotFoundError,
	OwnerCannotBeRemovedError,
	ServiceUnavailableError,
)
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.service import member_service
from sqlalchemy.exc import DBAPIError, OperationalError


def _user(username: str = "alice") -> User:
	return User(id=uuid4(), username=username, email=f"{username}@example.com", role="member", is_active=True)


def _project(owner: User) -> Project:
	return Project(id=uuid4(), name="Project", owner_id=owner.id, owner=owner, is_active=True)


def _member(project: Project, user: User) -> ProjectMember:
	return ProjectMember(
		project_id=project.id,
		user_id=user.id,
		user=user,
		joined_at=datetime.now(timezone.utc),
	)


@pytest.mark.asyncio
async def test_list_members_returns_member_summary(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _user()
	project = _project(owner)
	member = _member(project, _user("bob"))
	list_by_project = AsyncMock(return_value=[member])
	monkeypatch.setattr(member_service.project_member_repository, "list_by_project", list_by_project)

	response = await member_service.list_members(project, AsyncMock())

	assert response.meta.total == 1
	assert response.items[0].username == "bob"


@pytest.mark.asyncio
async def test_add_member_rejects_existing_member(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=True))

	db = AsyncMock()
	with pytest.raises(AlreadyMemberError):
		await member_service.add_member(project, target.id, owner.id, db)

	db.rollback.assert_not_awaited()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_member_rejects_missing_user_without_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _user()
	project = _project(owner)
	db = AsyncMock()
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=None))

	with pytest.raises(NotFoundError):
		await member_service.add_member(project, uuid4(), owner.id, db)

	db.rollback.assert_not_awaited()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("database_error", "expected_error"),
	[
		(
			OperationalError("insert member", {}, SimpleNamespace(sqlstate="08006")),
			ServiceUnavailableError,
		),
		(DBAPIError("insert member", {}, Exception("database error")), DBAPIError),
	],
	ids=["connection_error", "other_database_error"],
)
async def test_add_member_rolls_back_database_errors(
	monkeypatch: pytest.MonkeyPatch, database_error: DBAPIError, expected_error: type[Exception]
) -> None:
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	db = AsyncMock()
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=False))
	monkeypatch.setattr(member_service.project_member_repository, "create", AsyncMock(side_effect=database_error))

	with pytest.raises(expected_error):
		await member_service.add_member(project, target.id, owner.id, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_member_rolls_back_not_found_after_create(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	db = AsyncMock()
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=False))
	monkeypatch.setattr(member_service.project_member_repository, "create", AsyncMock())
	monkeypatch.setattr(member_service.project_member_repository, "list_by_project", AsyncMock(return_value=[]))

	with pytest.raises(NotFoundError):
		await member_service.add_member(project, target.id, owner.id, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_member_rolls_back_already_member_after_create(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	db = AsyncMock()
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=False))
	monkeypatch.setattr(
		member_service.project_member_repository,
		"create",
		AsyncMock(side_effect=AlreadyMemberError()),
	)

	with pytest.raises(AlreadyMemberError):
		await member_service.add_member(project, target.id, owner.id, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_member_rejects_owner() -> None:
	owner = _user()
	project = _project(owner)

	with pytest.raises(OwnerCannotBeRemovedError):
		await member_service.remove_member(project, owner.id, AsyncMock())


@pytest.mark.asyncio
async def test_remove_member_rejects_missing_member(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _user()
	project = _project(owner)
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=False))

	with pytest.raises(NotFoundError):
		await member_service.remove_member(project, uuid4(), AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("database_error", "expected_error"),
	[
		(
			OperationalError("delete member", {}, SimpleNamespace(sqlstate="08006")),
			ServiceUnavailableError,
		),
		(DBAPIError("delete member", {}, Exception("database error")), DBAPIError),
	],
	ids=["connection_error", "other_database_error"],
)
async def test_remove_member_rolls_back_database_errors(
	monkeypatch: pytest.MonkeyPatch, database_error: DBAPIError, expected_error: type[Exception]
) -> None:
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	db = AsyncMock()
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=True))
	monkeypatch.setattr(member_service.project_member_repository, "delete", AsyncMock(side_effect=database_error))

	with pytest.raises(expected_error):
		await member_service.remove_member(project, target.id, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()

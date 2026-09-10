from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.models.project import Project
from app.models.user import User
from app.repository import project_repository
from app.schemas.auth import CurrentUser
from app.schemas.project import ProjectCreateRequest, ProjectUpdateRequest
from app.service import project_service


def _user() -> User:
	return User(id=uuid4(), username="alice", email="alice@example.com", last_name="山田", first_name="太郎")


def _current_user(user: User) -> CurrentUser:
	return CurrentUser(id=user.id, username=user.username, role="member", is_active=True, email_verified_at=None)


def _project(user: User) -> Project:
	return Project(
		id=uuid4(),
		name="Project",
		description="description",
		owner_id=user.id,
		owner=user,
		is_active=True,
		created_at=datetime.now(timezone.utc),
		updated_at=datetime.now(timezone.utc),
	)


@pytest.mark.asyncio
async def test_list_projects_maps_repository_counts(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	project = _project(user)
	item = project_repository.ProjectListItem(project, 2, 3, 4, 5, 6)
	list_for_user = AsyncMock(return_value=[item])
	monkeypatch.setattr(project_service.project_repository, "list_for_user", list_for_user)

	response = await project_service.list_projects(_current_user(user), 1, 20, False, AsyncMock())

	assert response.items[0].task_counts.model_dump() == {"todo": 3, "in_progress": 4, "done": 5}
	assert response.meta.total == 1
	list_for_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_project_returns_summary(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	project = _project(user)
	create = AsyncMock(return_value=project.id)
	get_by_id = AsyncMock(return_value=project)
	monkeypatch.setattr(project_service.project_repository, "create", create)
	monkeypatch.setattr(project_service.project_repository, "get_by_id", get_by_id)

	response = await project_service.create_project(
		_current_user(user), ProjectCreateRequest(name="Project"), AsyncMock()
	)

	assert response.id == project.id
	assert response.is_owner is True
	create.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_project_passes_partial_values(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	project = _project(user)
	db = AsyncMock()
	update = AsyncMock()
	set_active = AsyncMock()
	monkeypatch.setattr(project_service.project_repository, "update", update)
	monkeypatch.setattr(project_service.project_repository, "set_active", set_active)
	monkeypatch.setattr(project_service.project_repository, "get_by_id", AsyncMock(return_value=project))

	await project_service.update_project(
		db, project, ProjectUpdateRequest(description="new", is_active=False), _current_user(user)
	)

	assert update.await_args.args == (db, project.id, project.name, "new", project.start_at, project.end_at)
	set_active.assert_awaited_once_with(db, project.id, False)

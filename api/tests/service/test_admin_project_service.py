from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.models.project import Project
from app.models.user import User
from app.repository import admin_repository, project_member_repository, project_repository, task_repository
from app.repository.admin_repository import AdminProjectListItem
from app.schemas.admin import AdminProjectListQuery
from app.schemas.auth import CurrentUser
from app.service import admin_project_service
from sqlalchemy.exc import OperationalError


def _owner() -> User:
	return User(id=uuid4(), username="taro", email="taro@example.com", last_name="山田", first_name="太郎")


def _project(owner: User, **overrides: object) -> Project:
	defaults: dict[str, object] = {
		"id": uuid4(),
		"name": "Cerberus開発",
		"description": "説明",
		"owner_id": owner.id,
		"owner": owner,
		"is_active": True,
		"start_at": None,
		"end_at": None,
		"created_at": datetime.now(timezone.utc),
		"updated_at": datetime.now(timezone.utc),
	}
	defaults.update(overrides)
	return Project(**defaults)


def _actor() -> CurrentUser:
	return CurrentUser(id=uuid4(), username="admin", role="admin", is_active=True, email_verified_at=None)


@pytest.mark.asyncio
async def test_list_admin_projects_returns_all_owners_projects(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _owner()
	rows = [AdminProjectListItem(_project(owner), 3) for _ in range(3)]
	monkeypatch.setattr(admin_repository, "list_projects", AsyncMock(return_value=rows))

	response = await admin_project_service.list_projects(AdminProjectListQuery(), AsyncMock())

	assert response.meta.total == 3
	assert len(response.items) == 3


@pytest.mark.asyncio
async def test_list_admin_projects_pagination_uses_total_count_from_window_function(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = _owner()
	rows = [AdminProjectListItem(_project(owner), 25) for _ in range(20)]
	monkeypatch.setattr(admin_repository, "list_projects", AsyncMock(return_value=rows))
	count_projects = AsyncMock()
	monkeypatch.setattr(admin_repository, "count_projects", count_projects)

	response = await admin_project_service.list_projects(AdminProjectListQuery(page=1, per_page=20), AsyncMock())

	assert len(response.items) == 20
	assert response.meta.total == 25
	assert response.meta.total_pages == 2
	count_projects.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_admin_projects_falls_back_to_count_when_page_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(admin_repository, "list_projects", AsyncMock(return_value=[]))
	monkeypatch.setattr(admin_repository, "count_projects", AsyncMock(return_value=25))

	response = await admin_project_service.list_projects(AdminProjectListQuery(page=5, per_page=20), AsyncMock())

	assert response.items == []
	assert response.meta.total == 25


@pytest.mark.asyncio
async def test_list_admin_projects_response_has_no_is_owner_field() -> None:
	assert "is_owner" not in admin_project_service.AdminProjectSummary.model_fields


@pytest.mark.asyncio
async def test_list_admin_projects_aggregates_member_and_task_counts(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _owner()
	project = _project(owner)
	list_projects = AsyncMock(
		return_value=[
			AdminProjectListItem(
				project,
				1,
				member_count=1,
				task_count_todo=1,
				task_count_done=2,
			)
		]
	)
	monkeypatch.setattr(admin_repository, "list_projects", list_projects)
	list_members = AsyncMock()
	list_tasks = AsyncMock()
	monkeypatch.setattr(project_member_repository, "list_by_project", list_members)
	monkeypatch.setattr(task_repository, "list_board", list_tasks)

	response = await admin_project_service.list_projects(AdminProjectListQuery(), AsyncMock())

	item = response.items[0]
	assert item.member_count == 1
	assert item.task_counts.todo == 1
	assert item.task_counts.in_progress == 0
	assert item.task_counts.done == 2
	list_projects.assert_awaited_once()
	list_members.assert_not_awaited()
	list_tasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_admin_projects_query_count_does_not_depend_on_project_count(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = _owner()
	rows = [AdminProjectListItem(_project(owner), 10) for _ in range(10)]
	list_projects = AsyncMock(return_value=rows)
	monkeypatch.setattr(admin_repository, "list_projects", list_projects)
	list_members = AsyncMock()
	list_tasks = AsyncMock()
	monkeypatch.setattr(project_member_repository, "list_by_project", list_members)
	monkeypatch.setattr(task_repository, "list_board", list_tasks)

	response = await admin_project_service.list_projects(AdminProjectListQuery(per_page=10), AsyncMock())

	assert len(response.items) == 10
	list_projects.assert_awaited_once()
	list_members.assert_not_awaited()
	list_tasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_admin_projects_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(
		admin_repository, "list_projects", AsyncMock(side_effect=OperationalError("x", {}, Exception()))
	)

	with pytest.raises(ServiceUnavailableError):
		await admin_project_service.list_projects(AdminProjectListQuery(), AsyncMock())


@pytest.mark.asyncio
async def test_admin_delete_project_service_unavailable_when_lookup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(project_repository, "get_by_id", AsyncMock(side_effect=OperationalError("x", {}, Exception())))

	with pytest.raises(ServiceUnavailableError):
		await admin_project_service.deactivate_project(_actor(), uuid4(), AsyncMock())


@pytest.mark.asyncio
async def test_admin_delete_project_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(project_repository, "get_by_id", AsyncMock(return_value=None))
	deactivate = AsyncMock()
	monkeypatch.setattr(admin_repository, "deactivate_project", deactivate)

	with pytest.raises(NotFoundError):
		await admin_project_service.deactivate_project(_actor(), uuid4(), AsyncMock())
	deactivate.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_delete_project_calls_repository_without_membership_check(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _owner()
	project = _project(owner)
	monkeypatch.setattr(project_repository, "get_by_id", AsyncMock(return_value=project))
	monkeypatch.setattr(project_member_repository, "list_by_project", AsyncMock(return_value=[]))
	monkeypatch.setattr(task_repository, "list_board", AsyncMock(return_value=[]))
	is_member = AsyncMock()
	monkeypatch.setattr(project_repository, "is_member", is_member)
	deactivate = AsyncMock()
	monkeypatch.setattr(admin_repository, "deactivate_project", deactivate)

	db = AsyncMock()
	await admin_project_service.deactivate_project(_actor(), project.id, db)

	deactivate.assert_awaited_once_with(db, project.id, False)
	is_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_delete_project_audit_log_contains_owner(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	owner = _owner()
	project = _project(owner)
	monkeypatch.setattr(project_repository, "get_by_id", AsyncMock(return_value=project))
	monkeypatch.setattr(project_member_repository, "list_by_project", AsyncMock(return_value=[]))
	monkeypatch.setattr(task_repository, "list_board", AsyncMock(return_value=[]))
	monkeypatch.setattr(admin_repository, "deactivate_project", AsyncMock())
	actor = _actor()

	with caplog.at_level("WARNING", logger="app.audit"):
		await admin_project_service.deactivate_project(actor, project.id, AsyncMock())

	record = caplog.records[-1]
	assert record.actor_id == str(actor.id)
	assert record.project_id == str(project.id)
	assert record.owner_id == str(owner.id)


@pytest.mark.asyncio
async def test_admin_delete_project_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	owner = _owner()
	project = _project(owner)
	monkeypatch.setattr(project_repository, "get_by_id", AsyncMock(return_value=project))
	monkeypatch.setattr(project_member_repository, "list_by_project", AsyncMock(return_value=[]))
	monkeypatch.setattr(task_repository, "list_board", AsyncMock(return_value=[]))
	monkeypatch.setattr(
		admin_repository, "deactivate_project", AsyncMock(side_effect=OperationalError("x", {}, Exception()))
	)

	with pytest.raises(ServiceUnavailableError):
		await admin_project_service.deactivate_project(_actor(), project.id, AsyncMock())

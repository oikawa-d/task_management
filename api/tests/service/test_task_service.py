from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import AssigneeInactiveError, TaskConflictError
from app.models.task import Task
from app.repository.task_repository import TaskWithProjectStatus
from app.schemas.auth import CurrentUser
from app.schemas.task import CalendarTaskQuery, TaskCreateRequest, TaskUpdateRequest
from app.service import task_service


def _user() -> CurrentUser:
	return CurrentUser(id=uuid4(), username="alice", role="member", is_active=True, email_verified_at=None)


def _item(user: CurrentUser) -> TaskWithProjectStatus:
	now = datetime.now(timezone.utc)
	return TaskWithProjectStatus(
		task=Task(
			id=uuid4(),
			project_id=uuid4(),
			title="Task",
			status="todo",
			created_by=user.id,
			position=0,
			version=1,
			is_active=True,
			due_at=now,
			created_at=now,
			updated_at=now,
		),
		project_is_active=True,
	)


@pytest.mark.asyncio
async def test_get_board_groups_tasks_by_status(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	item = _item(user)
	monkeypatch.setattr(task_service.task_repository, "list_board", AsyncMock(return_value=[item]))

	response = await task_service.get_board(item.task.project_id, False, AsyncMock())

	assert [task.id for task in response.columns.todo] == [item.task.id]


@pytest.mark.asyncio
async def test_create_task_calls_repository_and_returns_response(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	item = _item(user)
	create = AsyncMock(return_value=item.task.id)
	get_by_id = AsyncMock(return_value=item)
	monkeypatch.setattr(task_service.task_repository, "create", create)
	monkeypatch.setattr(task_service.task_repository, "get_by_id", get_by_id)

	response = await task_service.create_task(item.task.project_id, TaskCreateRequest(title="Task"), user, AsyncMock())

	assert response.id == item.task.id
	create.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [AssigneeInactiveError, TaskConflictError])
async def test_create_task_rolls_back_repository_constraint_error(
	error: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
	user = _user()
	db = AsyncMock()
	monkeypatch.setattr(task_service.task_repository, "create", AsyncMock(side_effect=error()))

	with pytest.raises(error):
		await task_service.create_task(user.id, TaskCreateRequest(title="Task"), user, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [AssigneeInactiveError, TaskConflictError])
async def test_update_task_rolls_back_repository_constraint_error(
	error: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
	user = _user()
	item = _item(user)
	db = AsyncMock()
	monkeypatch.setattr(task_service.task_repository, "get_by_id", AsyncMock(return_value=item))
	monkeypatch.setattr(task_service, "require_task_access", AsyncMock())
	monkeypatch.setattr(task_service.task_repository, "update", AsyncMock(side_effect=error()))

	with pytest.raises(error):
		await task_service.update_task(item.task.id, TaskUpdateRequest(version=1, title="Updated"), user, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


async def test_list_tasks_passes_unassigned_filter_to_repository(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	db = AsyncMock()
	list_for_user = AsyncMock(return_value=[])
	monkeypatch.setattr(task_service.task_repository, "list_for_user", list_for_user)

	response = await task_service.list_tasks(user, "unassigned", None, False, 2, 5, db)

	assert response.items == []
	list_for_user.assert_awaited_once_with(db, user.id, None, None, False, 5, 5, True)


@pytest.mark.asyncio
async def test_list_calendar_tasks_converts_app_dates_to_utc_and_checks_membership(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = _user()
	item = _item(user)
	project_id = item.task.project_id
	list_calendar = AsyncMock(return_value=[item])
	is_member = AsyncMock(return_value=True)
	monkeypatch.setattr(task_service.task_repository, "list_calendar", list_calendar)
	monkeypatch.setattr(task_service.project_repository, "is_member", is_member)
	query = CalendarTaskQuery(
		**{"from": "2026-09-01", "to": "2026-09-01", "scope": "project", "project_id": project_id}
	)

	response = await task_service.list_calendar_tasks(user, query, AsyncMock())

	is_member.assert_awaited_once()
	list_calendar.assert_awaited_once()
	args = list_calendar.await_args.args
	assert args[1] == user.id
	assert args[2].isoformat() == "2026-08-31T15:00:00+00:00"
	assert args[3].isoformat() == "2026-09-01T15:00:00+00:00"
	assert response[0].id == item.task.id


@pytest.mark.asyncio
async def test_list_calendar_tasks_returns_app_timezone_due_date_at_utc_boundary(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = _user()
	item = _item(user)
	item.task.due_at = datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc)
	monkeypatch.setattr(task_service.task_repository, "list_calendar", AsyncMock(return_value=[item]))

	query = CalendarTaskQuery(**{"from": "2026-09-10", "to": "2026-09-10", "scope": "me"})
	response = await task_service.list_calendar_tasks(user, query, AsyncMock())

	assert response[0].due_date.isoformat() == "2026-09-10"

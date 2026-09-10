from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.models.notification import Notification
from app.repository.notification_repository import NotificationListItem
from app.schemas.auth import CurrentUser
from app.service import notification_service


def _user() -> CurrentUser:
	return CurrentUser(id=uuid4(), username="taro", role="member", is_active=True, email_verified_at=None)


def _list_item(
	*,
	task_id=None,
	task_title: str | None = None,
	task_project_id=None,
	total_count: int = 1,
) -> NotificationListItem:
	now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
	notification = Notification(
		id=uuid4(),
		user_id=uuid4(),
		task_id=task_id,
		type="due_today_created",
		title="期限です",
		body="確認してください",
		due_at=now,
		dedupe_key="k",
		read_at=None,
		created_at=now,
	)
	return NotificationListItem(
		notification=notification,
		task_title=task_title,
		task_project_id=task_project_id,
		total_count=total_count,
	)


@pytest.mark.asyncio
async def test_list_notifications_scopes_repository_to_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	list_by_user = AsyncMock(return_value=[_list_item()])
	count_unread = AsyncMock(return_value=1)
	monkeypatch.setattr(notification_service.notification_repository, "list_by_user", list_by_user)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", count_unread)
	db = object()

	response = await notification_service.list_notifications(db, user, 2, 20, False)  # type: ignore[arg-type]

	list_by_user.assert_awaited_once_with(db, user.id, False, limit=20, offset=20)
	assert response.items[0].title == "期限です"
	assert response.unread_count == 1


@pytest.mark.asyncio
async def test_list_notifications_includes_task_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	task_id = uuid4()
	project_id = uuid4()
	item = _list_item(task_id=task_id, task_title="設計書をレビューする", task_project_id=project_id)
	monkeypatch.setattr(notification_service.notification_repository, "list_by_user", AsyncMock(return_value=[item]))
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", AsyncMock(return_value=0))
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	assert response.items[0].task is not None
	assert response.items[0].task.id == task_id
	assert response.items[0].task.project_id == project_id
	assert response.items[0].task.title == "設計書をレビューする"


@pytest.mark.asyncio
async def test_list_notifications_task_deleted_returns_null(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	item = _list_item(task_id=None)
	monkeypatch.setattr(notification_service.notification_repository, "list_by_user", AsyncMock(return_value=[item]))
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", AsyncMock(return_value=0))
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	assert response.items[0].task is None


@pytest.mark.asyncio
async def test_list_notifications_meta_total_reflects_overall_count_not_page_size(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = _user()
	items = [_list_item(total_count=25) for _ in range(5)]
	monkeypatch.setattr(notification_service.notification_repository, "list_by_user", AsyncMock(return_value=items))
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", AsyncMock(return_value=0))
	db = object()

	response = await notification_service.list_notifications(db, user, 2, 20, False)  # type: ignore[arg-type]

	assert len(response.items) == 5
	assert response.meta.total == 25
	assert response.meta.total_pages == 2


@pytest.mark.asyncio
async def test_list_notifications_meta_total_is_zero_when_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	monkeypatch.setattr(notification_service.notification_repository, "list_by_user", AsyncMock(return_value=[]))
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", AsyncMock(return_value=0))
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	assert response.items == []
	assert response.meta.total == 0
	assert response.meta.total_pages == 0


@pytest.mark.asyncio
async def test_mark_all_notifications_returns_changed_count(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	count_unread = AsyncMock(side_effect=[3, 0])
	mark_all_read = AsyncMock()
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", count_unread)
	monkeypatch.setattr(notification_service.notification_repository, "mark_all_read", mark_all_read)
	db = object()

	response = await notification_service.mark_all_notifications_read(db, user)  # type: ignore[arg-type]

	mark_all_read.assert_awaited_once_with(db, user.id)
	assert response.updated_count == 3
	assert response.unread_count == 0


@pytest.mark.asyncio
async def test_mark_notification_read_returns_app_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	mark_read = AsyncMock()
	monkeypatch.setattr(notification_service.notification_repository, "mark_read", mark_read)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", AsyncMock(return_value=0))
	notification_id = uuid4()
	db = object()

	response = await notification_service.mark_notification_read(db, notification_id, user)  # type: ignore[arg-type]

	mark_read.assert_awaited_once_with(db, notification_id, user.id)
	assert response.id == notification_id
	assert response.read_at.tzinfo is not None

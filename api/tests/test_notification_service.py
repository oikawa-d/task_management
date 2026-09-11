from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from app.core.exceptions import NotFoundError
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


def _patch_repository(
	monkeypatch: pytest.MonkeyPatch,
	*,
	list_by_user_return=None,
	count_notifications_return: int = 0,
	count_unread_return: int = 0,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
	list_by_user = AsyncMock(return_value=list_by_user_return or [])
	count_notifications = AsyncMock(return_value=count_notifications_return)
	count_unread = AsyncMock(return_value=count_unread_return)
	monkeypatch.setattr(notification_service.notification_repository, "list_by_user", list_by_user)
	monkeypatch.setattr(notification_service.notification_repository, "count_notifications", count_notifications)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", count_unread)
	return list_by_user, count_notifications, count_unread


@pytest.mark.asyncio
async def test_list_notifications_scopes_repository_to_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	list_by_user, _, _ = _patch_repository(monkeypatch, list_by_user_return=[_list_item()], count_unread_return=1)
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
	_patch_repository(monkeypatch, list_by_user_return=[item])
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
	_patch_repository(monkeypatch, list_by_user_return=[item])
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	assert response.items[0].task is None


@pytest.mark.asyncio
async def test_list_notifications_task_title_none_returns_null_task(monkeypatch: pytest.MonkeyPatch) -> None:
	"""task_idが非NULLでもtask_titleがNULL（LEFT JOIN不一致）ならtask=nullとする。"""
	user = _user()
	item = _list_item(task_id=uuid4(), task_title=None, task_project_id=uuid4())
	_patch_repository(monkeypatch, list_by_user_return=[item])
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	assert response.items[0].task is None


@pytest.mark.asyncio
async def test_list_notifications_meta_total_reflects_overall_count_not_page_size(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = _user()
	items = [_list_item(total_count=25) for _ in range(5)]
	_patch_repository(monkeypatch, list_by_user_return=items)
	db = object()

	response = await notification_service.list_notifications(db, user, 2, 20, False)  # type: ignore[arg-type]

	assert len(response.items) == 5
	assert response.meta.total == 25
	assert response.meta.total_pages == 2


@pytest.mark.asyncio
async def test_list_notifications_meta_total_uses_fallback_when_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
	"""pageが総ページ数を超えitemsが空でも、meta.totalは0ではなく実際の全体件数を返す。"""
	user = _user()
	_, count_notifications, _ = _patch_repository(monkeypatch, list_by_user_return=[], count_notifications_return=7)
	db = object()

	response = await notification_service.list_notifications(db, user, 99, 20, False)  # type: ignore[arg-type]

	count_notifications.assert_awaited_once_with(db, user.id, False)
	assert response.items == []
	assert response.meta.total == 7
	assert response.meta.total_pages == 1


@pytest.mark.asyncio
async def test_list_notifications_calls_count_unread_only_when_not_unread_only(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = _user()
	_, count_notifications, count_unread = _patch_repository(
		monkeypatch, list_by_user_return=[_list_item(total_count=3)], count_unread_return=2
	)
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, False)  # type: ignore[arg-type]

	count_unread.assert_awaited_once_with(db, user.id)
	count_notifications.assert_not_awaited()
	assert response.unread_count == 2


@pytest.mark.asyncio
async def test_list_notifications_skips_count_unread_when_unread_only(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	_, count_notifications, count_unread = _patch_repository(
		monkeypatch, list_by_user_return=[_list_item(total_count=4)]
	)
	db = object()

	response = await notification_service.list_notifications(db, user, 1, 20, True)  # type: ignore[arg-type]

	count_unread.assert_not_awaited()
	count_notifications.assert_not_awaited()
	assert response.unread_count == 4
	assert response.meta.total == 4


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
	persisted_read_at = datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc)
	mark_read = AsyncMock(return_value=persisted_read_at)
	monkeypatch.setattr(notification_service.notification_repository, "mark_read", mark_read)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", AsyncMock(return_value=0))
	notification_id = uuid4()
	db = object()

	response = await notification_service.mark_notification_read(db, notification_id, user)  # type: ignore[arg-type]

	mark_read.assert_awaited_once_with(db, notification_id, user.id)
	assert response.id == notification_id
	assert response.read_at == persisted_read_at.astimezone(ZoneInfo("Asia/Tokyo"))


@pytest.mark.asyncio
async def test_mark_notification_read_returns_404_when_repository_returns_none(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = _user()
	mark_read = AsyncMock(return_value=None)
	count_unread = AsyncMock(return_value=0)
	monkeypatch.setattr(notification_service.notification_repository, "mark_read", mark_read)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", count_unread)
	db = object()

	with pytest.raises(NotFoundError):
		await notification_service.mark_notification_read(db, uuid4(), user)  # type: ignore[arg-type]

	count_unread.assert_not_awaited()

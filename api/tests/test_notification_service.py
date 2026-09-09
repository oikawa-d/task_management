from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.schemas.auth import CurrentUser
from app.service import notification_service


def _user() -> CurrentUser:
	return CurrentUser(id=uuid4(), username="taro", role="member", is_active=True, email_verified_at=None)


def _notification() -> SimpleNamespace:
	now = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
	return SimpleNamespace(
		id=uuid4(),
		type="due_today_created",
		title="期限です",
		body="確認してください",
		due_at=now,
		read_at=None,
		created_at=now,
	)


@pytest.mark.asyncio
async def test_list_notifications_scopes_repository_to_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	list_by_user = AsyncMock(return_value=[_notification()])
	count_unread = AsyncMock(return_value=1)
	monkeypatch.setattr(notification_service.notification_repository, "list_by_user", list_by_user)
	monkeypatch.setattr(notification_service.notification_repository, "count_unread", count_unread)
	db = object()

	response = await notification_service.list_notifications(db, user, 2, 20, False)  # type: ignore[arg-type]

	list_by_user.assert_awaited_once_with(db, user.id, False, limit=20, offset=20)
	assert response.items[0].title == "期限です"
	assert response.unread_count == 1


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

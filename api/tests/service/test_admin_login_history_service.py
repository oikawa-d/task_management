from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import ServiceUnavailableError
from app.models.login_history import LoginHistory
from app.models.user import User
from app.repository import admin_repository
from app.repository.admin_repository import AdminLoginHistoryListItem
from app.schemas.admin import AdminLoginHistoryQuery
from app.service import admin_login_history_service
from sqlalchemy.exc import OperationalError


def _user(**overrides: object) -> User:
	defaults: dict[str, object] = {
		"id": uuid4(),
		"username": "taro",
		"email": "taro@example.com",
		"last_name": "山田",
		"first_name": "太郎",
	}
	defaults.update(overrides)
	return User(**defaults)


def _history(**overrides: object) -> LoginHistory:
	defaults: dict[str, object] = {
		"id": uuid4(),
		"user_id": uuid4(),
		"login_identifier": "taro",
		"login_method": "session",
		"ip_address": "203.0.113.10",
		"user_agent": "pytest",
		"success": True,
		"failure_reason": None,
		"created_at": datetime.now(timezone.utc),
	}
	defaults.update(overrides)
	return LoginHistory(**defaults)


@pytest.mark.asyncio
async def test_list_admin_login_history_null_user_for_unregistered_identifier(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	history = _history(user_id=None, success=False, failure_reason="user_not_found")
	monkeypatch.setattr(
		admin_repository, "list_login_history", AsyncMock(return_value=[AdminLoginHistoryListItem(history, 1)])
	)

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

	assert response.items[0].user is None


@pytest.mark.asyncio
async def test_list_admin_login_history_returns_all_users(monkeypatch: pytest.MonkeyPatch) -> None:
	user_a = _user()
	user_b = _user(id=uuid4(), username="jiro", last_name=None, first_name=None)
	history_a = _history(user_id=user_a.id)
	history_b = _history(user_id=user_b.id)
	monkeypatch.setattr(
		admin_repository,
		"list_login_history",
		AsyncMock(
			return_value=[
				AdminLoginHistoryListItem(history_a, 2, user_a),
				AdminLoginHistoryListItem(history_b, 2, user_b),
			]
		),
	)

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

	assert response.meta.total == 2
	usernames = {item.user.username for item in response.items if item.user is not None}
	assert usernames == {"taro", "jiro"}
	jiro_item = next(item for item in response.items if item.user and item.user.username == "jiro")
	assert jiro_item.user is not None
	assert jiro_item.user.display_name == "jiro"


@pytest.mark.asyncio
async def test_list_admin_login_history_uses_user_info_from_list_query(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	rows = [AdminLoginHistoryListItem(_history(user_id=user.id), 3, user) for _ in range(3)]
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=rows))

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

	assert all(item.user is not None and item.user.username == "taro" for item in response.items)


@pytest.mark.asyncio
async def test_list_admin_login_history_pagination_uses_total_count_from_window_function(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	rows = [AdminLoginHistoryListItem(_history(user_id=None), 25) for _ in range(20)]
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=rows))
	count_login_history = AsyncMock()
	monkeypatch.setattr(admin_repository, "count_login_history", count_login_history)

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(page=1, per_page=20), AsyncMock())

	assert len(response.items) == 20
	assert response.meta.total == 25
	assert response.meta.total_pages == 2
	count_login_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_admin_login_history_falls_back_to_count_when_page_is_empty(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=[]))
	monkeypatch.setattr(admin_repository, "count_login_history", AsyncMock(return_value=25))

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(page=5, per_page=20), AsyncMock())

	assert response.items == []
	assert response.meta.total == 25


@pytest.mark.asyncio
async def test_list_admin_login_history_invalid_date_range_rejected_by_schema() -> None:
	now = datetime.now(timezone.utc)
	with pytest.raises(ValueError):
		AdminLoginHistoryQuery(**{"from": now, "to": now - timedelta(days=1)})


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_list_admin_login_history_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(
		admin_repository, "list_login_history", AsyncMock(side_effect=OperationalError("x", {}, Exception()))
	)

	with pytest.raises(ServiceUnavailableError):
		await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

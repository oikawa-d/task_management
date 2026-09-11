from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import ServiceUnavailableError
from app.models.login_history import LoginHistory
from app.models.user import User
from app.repository import admin_repository, user_repository
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
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=[history]))
	get_by_id = AsyncMock()
	monkeypatch.setattr(user_repository, "get_by_id", get_by_id)

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

	assert response.items[0].user is None
	get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_admin_login_history_returns_all_users(monkeypatch: pytest.MonkeyPatch) -> None:
	user_a = _user()
	user_b = _user(id=uuid4(), username="jiro", last_name=None, first_name=None)
	history_a = _history(user_id=user_a.id)
	history_b = _history(user_id=user_b.id)
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=[history_a, history_b]))
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(side_effect=[user_a, user_b]))

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

	assert response.meta.total == 2
	usernames = {item.user.username for item in response.items if item.user is not None}
	assert usernames == {"taro", "jiro"}
	jiro_item = next(item for item in response.items if item.user and item.user.username == "jiro")
	assert jiro_item.user is not None
	assert jiro_item.user.display_name == "jiro"


@pytest.mark.asyncio
async def test_list_admin_login_history_batches_user_lookup_deduplicated(monkeypatch: pytest.MonkeyPatch) -> None:
	user = _user()
	histories = [_history(user_id=user.id) for _ in range(3)]
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=histories))
	get_by_id = AsyncMock(return_value=user)
	monkeypatch.setattr(user_repository, "get_by_id", get_by_id)

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

	assert get_by_id.await_count == 1
	assert all(item.user is not None and item.user.username == "taro" for item in response.items)


@pytest.mark.asyncio
async def test_list_admin_login_history_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
	histories = [_history(user_id=None) for _ in range(25)]
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=histories))

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(page=1, per_page=20), AsyncMock())

	assert len(response.items) == 20
	assert response.meta.total == 25
	assert response.meta.total_pages == 2


@pytest.mark.asyncio
async def test_list_admin_login_history_invalid_date_range_rejected_by_schema() -> None:
	now = datetime.now(timezone.utc)
	with pytest.raises(ValueError):
		AdminLoginHistoryQuery(**{"from": now, "to": now - timedelta(days=1)})


@pytest.mark.asyncio
async def test_list_admin_login_history_service_unavailable_on_user_lookup_error(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	history = _history(user_id=uuid4())
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=[history]))
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(side_effect=OperationalError("x", {}, Exception())))

	with pytest.raises(ServiceUnavailableError):
		await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())


@pytest.mark.asyncio
async def test_list_admin_login_history_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(
		admin_repository, "list_login_history", AsyncMock(side_effect=OperationalError("x", {}, Exception()))
	)

	with pytest.raises(ServiceUnavailableError):
		await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

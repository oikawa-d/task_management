from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.schemas.admin import (
	AdminLoginHistoryItem,
	AdminLoginHistoryQuery,
	AdminProjectListQuery,
	AdminUserItem,
	AdminUserListMeta,
	AdminUserListQuery,
	AdminUserRoleUpdateRequest,
	AdminUserStatusUpdateRequest,
)
from pydantic import ValidationError


def test_admin_user_query_applies_defaults_and_filters() -> None:
	query = AdminUserListQuery(q="taro", role="admin", is_active=False)

	assert query.page == 1
	assert query.per_page == 20
	assert query.role == "admin"


@pytest.mark.parametrize(
	"payload",
	[
		{"page": 0},
		{"per_page": 101},
		{"role": "owner"},
		{"q": "a" * 101},
		{"unexpected": True},
	],
)
def test_admin_user_query_rejects_invalid_filters(payload: dict[str, object]) -> None:
	with pytest.raises(ValidationError):
		AdminUserListQuery(**payload)


def test_admin_update_requests_limit_role_and_status_values() -> None:
	assert AdminUserRoleUpdateRequest(role="member").role == "member"
	assert AdminUserStatusUpdateRequest(is_active=False).is_active is False
	with pytest.raises(ValidationError):
		AdminUserRoleUpdateRequest(role="owner")


def test_admin_user_response_has_no_secret_fields() -> None:
	item = AdminUserItem(
		id=uuid4(),
		username="taro",
		email="taro@example.com",
		display_name="太郎",
		role="member",
		is_active=True,
		email_verified_at=None,
		created_at=datetime.now(timezone.utc),
	)

	assert "password_hash" not in item.model_dump()


def test_admin_login_history_query_supports_aliases_and_period_validation() -> None:
	query = AdminLoginHistoryQuery(**{"from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z"})

	assert query.created_from is not None
	assert query.created_to is not None
	with pytest.raises(ValidationError):
		AdminLoginHistoryQuery(**{"from": "2026-01-02T00:00:00Z", "to": "2026-01-01T00:00:00Z"})


def test_admin_login_history_item_allows_deleted_user() -> None:
	item = AdminLoginHistoryItem(
		id=uuid4(),
		user=None,
		login_identifier="unknown@example.com",
		login_method="session",
		ip_address=None,
		user_agent=None,
		success=False,
		failure_reason="invalid_credentials",
		created_at=datetime.now(timezone.utc),
	)

	assert item.user is None
	assert AdminProjectListQuery(q="project").q == "project"
	assert AdminUserListMeta(page=1, per_page=20, total=0, total_pages=0).total == 0

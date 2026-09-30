"""
管理者スキーマのバリデーション・デフォルト値・フィールド制限を検証するテスト。
"""

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
	"""
	AdminUserListQuery がクエリパラメータにデフォルト値を適用し、フィルタ条件を保持することを検証。

	条件：q="taro"、role="admin"、is_active=False でクエリを作成したとき、ページ（1）とper_page（20）のデフォルト値が適用され、フィルタ値が保持されること。
	"""
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
	"""
	AdminUserListQuery が不正なクエリパラメータを拒否し、ValidationError を送出することを検証。

	条件：page=0（範囲外）、per_page=101（上限超過）、role="owner"（許可外値）、q=長文字列101文字（長さ制限超過）、予期しないキー を含むペイロードでクエリを作成したとき、いずれのケースでも ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		AdminUserListQuery(**payload)


def test_admin_update_requests_limit_role_and_status_values() -> None:
	"""
	AdminUserRoleUpdateRequest と AdminUserStatusUpdateRequest がフィールド値を制限し、不正な値を拒否することを検証。

	条件：role="member" と is_active=False は有効な値として受け入れられ、role="owner" は許可外の値として ValidationError が送出されること。
	"""
	assert AdminUserRoleUpdateRequest(role="member").role == "member"
	assert AdminUserStatusUpdateRequest(is_active=False).is_active is False
	with pytest.raises(ValidationError):
		AdminUserRoleUpdateRequest(role="owner")


def test_admin_user_response_has_no_secret_fields() -> None:
	"""
	AdminUserItem が model_dump() でシークレットフィールド（password_hash）を含まないことを検証。

	条件：ユーザー情報を含む AdminUserItem インスタンスを作成し model_dump() を呼び出したとき、password_hash が含まれないこと。
	"""
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
	"""
	AdminLoginHistoryQuery がフィールドエイリアス（from→created_from、to→created_to）をサポートし、期間検証を行うことを検証。

	条件：エイリアス "from" と "to" を使用してクエリを作成したとき、created_from と created_to に変換され、from後：to という時系列条件でバリデーションされること。from が to より後の場合は ValidationError が送出されること。
	"""
	query = AdminLoginHistoryQuery(**{"from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z"})

	assert query.created_from is not None
	assert query.created_to is not None
	with pytest.raises(ValidationError):
		AdminLoginHistoryQuery(**{"from": "2026-01-02T00:00:00Z", "to": "2026-01-01T00:00:00Z"})


def test_admin_login_history_item_allows_deleted_user() -> None:
	"""
	AdminLoginHistoryItem がユーザーが削除されたログイン試行を表現でき、AdminProjectListQuery と AdminUserListMeta が正常に動作することを検証。

	条件：user=None（削除されたユーザー）でログイン履歴アイテムを作成したとき、user フィールドが None に保つこと。また、AdminProjectListQuery と AdminUserListMeta のデフォルト挙動が正常であること。
	"""
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

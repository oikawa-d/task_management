"""app.service.admin_login_history_service (管理者向けログイン履歴検索サービス)のテスト。

admin_repositoryをモック化し、ユーザー紐付け・ページネーション・
DB接続エラー時のフォールバック挙動を検証する。
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
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
	"""テスト用のUserモデルインスタンスを生成するヘルパー。

	Args:
		**overrides: デフォルト値に対して上書きしたいフィールドと値。

	Returns:
		上書き後の値で構築されたUserインスタンス。
	"""
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
	"""テスト用のLoginHistoryモデルインスタンスを生成するヘルパー。

	Args:
		**overrides: デフォルト値に対して上書きしたいフィールドと値。

	Returns:
		上書き後の値で構築されたLoginHistoryインスタンス。
	"""
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


def _connection_error(statement: str = "x") -> OperationalError:
	"""DB接続エラー(SQLSTATE 08006)を模したOperationalErrorを生成するヘルパー。

	Args:
		statement: エラーに紐付けるダミーのSQL文字列。

	Returns:
		SQLSTATEが接続エラーを示すOperationalErrorインスタンス。
	"""
	return OperationalError(statement, {}, SimpleNamespace(sqlstate="08006"))


@pytest.mark.asyncio
async def test_list_admin_login_history_null_user_for_unregistered_identifier(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""未登録の識別子によるログイン失敗履歴(user_id=None)を検索した場合、対応するuserがNoneになることを検証する。"""
	history = _history(user_id=None, success=False, failure_reason="user_not_found")
	monkeypatch.setattr(
		admin_repository, "list_login_history", AsyncMock(return_value=[AdminLoginHistoryListItem(history, 1)])
	)

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

	assert response.items[0].user is None


@pytest.mark.asyncio
async def test_list_admin_login_history_returns_all_users(monkeypatch: pytest.MonkeyPatch) -> None:
	"""複数ユーザーの履歴を検索した場合、それぞれのユーザー情報(表示名を含む)が正しく紐付けられて返ることを検証する。

	last_name/first_nameが未設定のユーザーでは、display_nameがusernameにフォールバックすることも確認する。
	"""
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
	"""list_login_historyが返す行に同梱されたユーザー情報がそのまま各itemのuserとして使われることを検証する。"""
	user = _user()
	rows = [AdminLoginHistoryListItem(_history(user_id=user.id), 3, user) for _ in range(3)]
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=rows))

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

	assert all(item.user is not None and item.user.username == "taro" for item in response.items)


@pytest.mark.asyncio
async def test_list_admin_login_history_pagination_uses_total_count_from_window_function(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""検索結果が1ページ分埋まる場合、list_login_historyが返す行に含まれる
	ウィンドウ関数由来の総件数からmeta.totalを算出し、count_login_historyを
	別途呼び出さないことを検証する。
	"""
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
	"""指定ページの検索結果が0件の場合、list_login_historyの戻り値からは
	総件数を算出できないため、count_login_historyを呼び出して総件数を
	補完することを検証する。
	"""
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(return_value=[]))
	monkeypatch.setattr(admin_repository, "count_login_history", AsyncMock(return_value=25))

	response = await admin_login_history_service.search(AdminLoginHistoryQuery(page=5, per_page=20), AsyncMock())

	assert response.items == []
	assert response.meta.total == 25


@pytest.mark.asyncio
async def test_list_admin_login_history_invalid_date_range_rejected_by_schema() -> None:
	"""AdminLoginHistoryQueryにfrom > toの日付範囲を渡した場合、スキーマのバリデーションで
	ValueErrorが送出されることを検証する。
	"""
	now = datetime.now(timezone.utc)
	with pytest.raises(ValueError):
		AdminLoginHistoryQuery(**{"from": now, "to": now - timedelta(days=1)})


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_list_admin_login_history_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	"""list_login_historyがDB接続エラー(sqlstate 08006)を送出した場合、
	ServiceUnavailableErrorへ変換されることを検証する。
	"""
	monkeypatch.setattr(admin_repository, "list_login_history", AsyncMock(side_effect=_connection_error()))

	with pytest.raises(ServiceUnavailableError):
		await admin_login_history_service.search(AdminLoginHistoryQuery(), AsyncMock())

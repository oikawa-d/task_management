from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import LastAdminRequiredError, NotFoundError, SelfModificationError, ServiceUnavailableError
from app.models.user import User
from app.repository import admin_repository, redis_store, user_repository
from app.schemas.admin import AdminUserListQuery
from app.schemas.auth import CurrentUser
from app.service import admin_user_service
from sqlalchemy.exc import DBAPIError, OperationalError


class _Orig(Exception):
	def __init__(self, sqlstate: str | None) -> None:
		super().__init__("boom")
		self.sqlstate = sqlstate


def _dbapi_error(sqlstate: str | None) -> DBAPIError:
	return DBAPIError("CALL sp_admin_update_user_role()", {}, _Orig(sqlstate))


def _user(**overrides: object) -> User:
	defaults: dict[str, object] = {
		"id": uuid4(),
		"username": "taro",
		"email": "taro@example.com",
		"last_name": "山田",
		"first_name": "太郎",
		"role": "member",
		"is_active": True,
		"email_verified_at": None,
		"created_at": datetime.now(timezone.utc),
		"updated_at": datetime.now(timezone.utc),
	}
	defaults.update(overrides)
	return User(**defaults)


def _actor() -> CurrentUser:
	return CurrentUser(id=uuid4(), username="admin", role="admin", is_active=True, email_verified_at=None)


@pytest.mark.asyncio
async def test_list_admin_users_display_name_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
	named = _user()
	fallback = _user(id=uuid4(), username="jiro", last_name=None, first_name=None)
	monkeypatch.setattr(admin_repository, "list_users", AsyncMock(return_value=[named, fallback]))

	response = await admin_user_service.list_users(AdminUserListQuery(), AsyncMock())

	names = {item.username: item.display_name for item in response.items}
	assert names["taro"] == "山田 太郎"
	assert names["jiro"] == "jiro"


@pytest.mark.asyncio
async def test_list_admin_users_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
	users = [_user(id=uuid4(), username=f"user{i}") for i in range(25)]
	monkeypatch.setattr(admin_repository, "list_users", AsyncMock(return_value=users))

	response = await admin_user_service.list_users(AdminUserListQuery(page=1, per_page=20), AsyncMock())

	assert len(response.items) == 20
	assert response.meta.total == 25
	assert response.meta.total_pages == 2


@pytest.mark.asyncio
async def test_list_admin_users_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(admin_repository, "list_users", AsyncMock(side_effect=OperationalError("x", {}, Exception())))

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.list_users(AdminUserListQuery(), AsyncMock())


@pytest.mark.asyncio
async def test_change_role_target_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=None))
	update_role = AsyncMock()
	monkeypatch.setattr(admin_repository, "update_user_role", update_role)

	with pytest.raises(NotFoundError):
		await admin_user_service.change_role(_actor(), uuid4(), "admin", AsyncMock())
	update_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_role_self_modification_checked_before_last_admin(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sp_admin_update_user_role内部で自己変更禁止を最後のadmin判定より先に評価する（#137）。

	要検討: 設計書のテスト表は「sp_admin_update_user_role未呼び出し」と記載しているが、
	実装済みのSP（db/procedures/sp_admin_update_user_role.sql）は自己変更禁止・最後の
	admin保護の両方を1回のCALL内部で判定する仕様（02_patch_admin_user_role.md §4）。
	そのため本テストはSPを呼び出した上でP0007を受け取り409へ変換されることを検証する。
	"""
	target = _user()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(side_effect=_dbapi_error("P0007")))

	with pytest.raises(SelfModificationError):
		await admin_user_service.change_role(_actor(), target.id, "member", AsyncMock())


@pytest.mark.asyncio
async def test_change_role_last_admin_required(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user(role="admin")
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(side_effect=_dbapi_error("P0008")))

	with pytest.raises(LastAdminRequiredError):
		await admin_user_service.change_role(_actor(), target.id, "member", AsyncMock())


@pytest.mark.asyncio
async def test_change_role_promotion_success(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user(role="member")
	updated = _user(id=target.id, role="admin")
	get_by_id = AsyncMock(side_effect=[target, updated])
	monkeypatch.setattr(user_repository, "get_by_id", get_by_id)
	update_role = AsyncMock()
	monkeypatch.setattr(admin_repository, "update_user_role", update_role)

	response = await admin_user_service.change_role(_actor(), target.id, "admin", AsyncMock())

	update_role.assert_awaited_once()
	assert response.role == "admin"


@pytest.mark.asyncio
async def test_change_status_target_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=None))

	with pytest.raises(NotFoundError):
		await admin_user_service.change_status(_actor(), uuid4(), False, AsyncMock())


@pytest.mark.asyncio
async def test_change_status_last_admin_required(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user(role="admin")
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock(side_effect=_dbapi_error("P0008")))

	with pytest.raises(LastAdminRequiredError):
		await admin_user_service.change_status(_actor(), target.id, False, AsyncMock())


@pytest.mark.asyncio
async def test_change_status_deactivate_db_then_redis_order(monkeypatch: pytest.MonkeyPatch) -> None:
	"""DB更新（commit）→Redis失効の順で呼ばれることを検証する（#333でDB先行が正と確定）。"""
	target = _user(is_active=True)
	updated = _user(id=target.id, is_active=False)
	call_order: list[str] = []

	get_by_id = AsyncMock(side_effect=[target, updated])
	monkeypatch.setattr(user_repository, "get_by_id", get_by_id)

	async def _update_status(*args: object, **kwargs: object) -> None:
		call_order.append("db_update")

	db = AsyncMock()

	async def _commit() -> None:
		call_order.append("db_commit")

	db.commit = _commit
	monkeypatch.setattr(admin_repository, "update_user_status", _update_status)

	async def _delete_all_sessions(*args: object, **kwargs: object) -> int:
		call_order.append("delete_all_sessions")
		return 0

	async def _revoke_all_refresh_tokens(*args: object, **kwargs: object) -> int:
		call_order.append("revoke_all_refresh_tokens")
		return 0

	monkeypatch.setattr(redis_store, "delete_all_sessions", _delete_all_sessions)
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", _revoke_all_refresh_tokens)

	await admin_user_service.change_status(_actor(), target.id, False, db)

	assert call_order == ["db_update", "db_commit", "delete_all_sessions", "revoke_all_refresh_tokens"]


@pytest.mark.asyncio
async def test_change_status_reactivate_skips_redis_revocation(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user(is_active=False)
	updated = _user(id=target.id, is_active=True)
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(side_effect=[target, updated]))
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock())
	delete_all_sessions = AsyncMock()
	revoke_all_refresh_tokens = AsyncMock()
	monkeypatch.setattr(redis_store, "delete_all_sessions", delete_all_sessions)
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", revoke_all_refresh_tokens)

	await admin_user_service.change_status(_actor(), target.id, True, AsyncMock())

	delete_all_sessions.assert_not_awaited()
	revoke_all_refresh_tokens.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_status_redis_failure_does_not_rollback_db(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Redis失効が失敗してもDBの無効化コミット自体は既に確定しており、ロールバックしない。"""
	target = _user(is_active=True)
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock())
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(side_effect=ConnectionError("redis down")))
	db = AsyncMock()

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.change_status(_actor(), target.id, False, db)

	db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_force_logout_target_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=None))

	with pytest.raises(NotFoundError):
		await admin_user_service.force_logout(_actor(), uuid4(), AsyncMock())


@pytest.mark.asyncio
async def test_force_logout_calls_redis_revocation_functions_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	call_order: list[str] = []

	async def _delete_all_sessions(*args: object, **kwargs: object) -> int:
		call_order.append("delete_all_sessions")
		return 0

	async def _revoke_all_refresh_tokens(*args: object, **kwargs: object) -> int:
		call_order.append("revoke_all_refresh_tokens")
		return 0

	monkeypatch.setattr(redis_store, "delete_all_sessions", _delete_all_sessions)
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", _revoke_all_refresh_tokens)

	await admin_user_service.force_logout(_actor(), target.id, AsyncMock())

	assert call_order == ["delete_all_sessions", "revoke_all_refresh_tokens"]


@pytest.mark.asyncio
async def test_force_logout_service_unavailable_on_redis_error(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(side_effect=ConnectionError("redis down")))

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.force_logout(_actor(), target.id, AsyncMock())


@pytest.mark.asyncio
async def test_get_existing_user_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(side_effect=OperationalError("x", {}, Exception())))

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.force_logout(_actor(), uuid4(), AsyncMock())


@pytest.mark.asyncio
async def test_change_role_unknown_sqlstate_is_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
	"""fail-close方針: P0007/P0008以外のDB例外は503へ変換する。"""
	target = _user()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(side_effect=_dbapi_error(None)))

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.change_role(_actor(), target.id, "admin", AsyncMock())


@pytest.mark.asyncio
async def test_force_logout_idempotent_when_no_active_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(return_value=0))
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", AsyncMock(return_value=0))

	await admin_user_service.force_logout(_actor(), target.id, AsyncMock())

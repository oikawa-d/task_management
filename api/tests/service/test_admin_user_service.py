from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import LastAdminRequiredError, NotFoundError, SelfModificationError, ServiceUnavailableError
from app.models.user import User
from app.repository import admin_repository, redis_store, user_repository
from app.repository.admin_repository import AdminUserListItem
from app.schemas.admin import AdminUserListQuery
from app.schemas.auth import CurrentUser
from app.service import admin_user_service
from redis.exceptions import ConnectionError as RedisConnectionError
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
	monkeypatch.setattr(
		admin_repository,
		"list_users",
		AsyncMock(return_value=[AdminUserListItem(named, 2), AdminUserListItem(fallback, 2)]),
	)

	response = await admin_user_service.list_users(AdminUserListQuery(), AsyncMock())

	names = {item.username: item.display_name for item in response.items}
	assert names["taro"] == "山田 太郎"
	assert names["jiro"] == "jiro"


@pytest.mark.asyncio
async def test_list_admin_users_pagination_uses_total_count_from_window_function(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	rows = [AdminUserListItem(_user(id=uuid4(), username=f"user{i}"), 25) for i in range(20)]
	monkeypatch.setattr(admin_repository, "list_users", AsyncMock(return_value=rows))
	count_users = AsyncMock()
	monkeypatch.setattr(admin_repository, "count_users", count_users)

	response = await admin_user_service.list_users(AdminUserListQuery(page=1, per_page=20), AsyncMock())

	assert len(response.items) == 20
	assert response.meta.total == 25
	assert response.meta.total_pages == 2
	count_users.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_admin_users_falls_back_to_count_when_page_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
	"""該当ページが総件数を超える場合、total_countがウィンドウ関数から取得できないためフォールバックする。"""
	monkeypatch.setattr(admin_repository, "list_users", AsyncMock(return_value=[]))
	monkeypatch.setattr(admin_repository, "count_users", AsyncMock(return_value=25))

	response = await admin_user_service.list_users(AdminUserListQuery(page=5, per_page=20), AsyncMock())

	assert response.items == []
	assert response.meta.total == 25


@pytest.mark.asyncio
async def test_list_admin_users_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(admin_repository, "list_users", AsyncMock(side_effect=OperationalError("x", {}, Exception())))

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.list_users(AdminUserListQuery(), AsyncMock())


@pytest.mark.asyncio
async def test_change_role_target_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
	"""SPが対象不存在（P0010）を返す。事前の存在確認SELECTは行わない（#347レビュー対応）。"""
	get_by_id = AsyncMock()
	monkeypatch.setattr(user_repository, "get_by_id", get_by_id)
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(side_effect=_dbapi_error("P0010")))

	with pytest.raises(NotFoundError):
		await admin_user_service.change_role(_actor(), uuid4(), "admin", AsyncMock())
	get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_role_self_modification_checked_before_last_admin(monkeypatch: pytest.MonkeyPatch) -> None:
	"""sp_admin_update_user_role内部で自己変更禁止を最後のadmin判定より先に評価する（#137）。"""
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(side_effect=_dbapi_error("P0007")))

	with pytest.raises(SelfModificationError):
		await admin_user_service.change_role(_actor(), uuid4(), "member", AsyncMock())


@pytest.mark.asyncio
async def test_change_role_last_admin_required(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(side_effect=_dbapi_error("P0008")))

	with pytest.raises(LastAdminRequiredError):
		await admin_user_service.change_role(_actor(), uuid4(), "member", AsyncMock())


@pytest.mark.asyncio
async def test_change_role_promotion_success(monkeypatch: pytest.MonkeyPatch) -> None:
	target_id = uuid4()
	updated = _user(id=target_id, role="admin")
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=updated))
	update_role = AsyncMock(return_value="member")
	monkeypatch.setattr(admin_repository, "update_user_role", update_role)

	response = await admin_user_service.change_role(_actor(), target_id, "admin", AsyncMock())

	update_role.assert_awaited_once()
	assert response.role == "admin"


@pytest.mark.asyncio
async def test_change_role_calls_repository_exactly_once_then_fetches_updated_user(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""事前の存在確認SELECTを廃止し、SP呼び出し1回＋成功後の応答取得1回に限定する（#347レビュー対応）。"""
	target_id = uuid4()
	get_by_id = AsyncMock(return_value=_user(id=target_id, role="admin"))
	monkeypatch.setattr(user_repository, "get_by_id", get_by_id)
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(return_value="member"))

	await admin_user_service.change_role(_actor(), target_id, "admin", AsyncMock())

	assert get_by_id.await_count == 1


@pytest.mark.asyncio
async def test_change_role_unknown_sqlstate_is_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
	"""fail-close方針: P0007/P0008/P0010以外のDB例外は503へ変換する。"""
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(side_effect=_dbapi_error(None)))

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.change_role(_actor(), uuid4(), "admin", AsyncMock())


@pytest.mark.asyncio
async def test_change_role_logs_old_role_new_role_and_result_on_success(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	target_id = uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=_user(id=target_id, role="admin")))
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(return_value="member"))
	actor = _actor()

	with caplog.at_level("INFO", logger="app.audit"):
		await admin_user_service.change_role(actor, target_id, "admin", AsyncMock())

	record = caplog.records[-1]
	assert record.actor_id == str(actor.id)
	assert record.target_id == str(target_id)
	assert record.old_role == "member"
	assert record.new_role == "admin"
	assert record.result == "success"


@pytest.mark.asyncio
async def test_change_role_logs_result_on_conflict(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	monkeypatch.setattr(admin_repository, "update_user_role", AsyncMock(side_effect=_dbapi_error("P0008")))
	actor = _actor()

	with caplog.at_level("INFO", logger="app.audit"), pytest.raises(LastAdminRequiredError):
		await admin_user_service.change_role(actor, uuid4(), "member", AsyncMock())

	record = caplog.records[-1]
	assert record.result == "LAST_ADMIN_REQUIRED"


@pytest.mark.asyncio
async def test_change_status_target_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock(side_effect=_dbapi_error("P0010")))

	with pytest.raises(NotFoundError):
		await admin_user_service.change_status(_actor(), uuid4(), False, AsyncMock())


@pytest.mark.asyncio
async def test_change_status_last_admin_required(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock(side_effect=_dbapi_error("P0008")))

	with pytest.raises(LastAdminRequiredError):
		await admin_user_service.change_status(_actor(), uuid4(), False, AsyncMock())


@pytest.mark.asyncio
async def test_change_status_deactivate_db_then_redis_order(monkeypatch: pytest.MonkeyPatch) -> None:
	"""DB更新（commit）→Redis失効の順で呼ばれることを検証する（#333でDB先行が正と確定）。"""
	target_id = uuid4()
	call_order: list[str] = []

	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=_user(id=target_id, is_active=False)))

	async def _update_status(*args: object, **kwargs: object) -> bool:
		call_order.append("db_update")
		return True

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

	await admin_user_service.change_status(_actor(), target_id, False, db)

	assert call_order == ["db_update", "db_commit", "delete_all_sessions", "revoke_all_refresh_tokens"]


@pytest.mark.asyncio
async def test_change_status_reactivate_skips_redis_revocation(monkeypatch: pytest.MonkeyPatch) -> None:
	target_id = uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=_user(id=target_id, is_active=True)))
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock(return_value=False))
	delete_all_sessions = AsyncMock()
	revoke_all_refresh_tokens = AsyncMock()
	monkeypatch.setattr(redis_store, "delete_all_sessions", delete_all_sessions)
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", revoke_all_refresh_tokens)

	await admin_user_service.change_status(_actor(), target_id, True, AsyncMock())

	delete_all_sessions.assert_not_awaited()
	revoke_all_refresh_tokens.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_status_redis_failure_does_not_rollback_db(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Redis失効が失敗してもDBの無効化コミット自体は既に確定しており、ロールバックしない。"""
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock(return_value=True))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(side_effect=RedisConnectionError("redis down")))
	db = AsyncMock()

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.change_status(_actor(), uuid4(), False, db)

	db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_status_redis_failure_logs_error_with_actor_target_and_operation(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	target_id = uuid4()
	actor = _actor()
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock(return_value=True))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(side_effect=RedisConnectionError("redis down")))

	with caplog.at_level("ERROR", logger="app.audit"), pytest.raises(ServiceUnavailableError):
		await admin_user_service.change_status(actor, target_id, False, AsyncMock())

	record = caplog.records[-1]
	assert record.levelname == "ERROR"
	assert record.actor_id == str(actor.id)
	assert record.target_id == str(target_id)
	assert record.operation == "delete_all_sessions"


@pytest.mark.asyncio
async def test_change_status_second_redis_call_failure_is_logged_with_its_own_operation(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock(return_value=True))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(return_value=1))
	monkeypatch.setattr(
		redis_store, "revoke_all_refresh_tokens", AsyncMock(side_effect=RedisConnectionError("redis down"))
	)

	with caplog.at_level("ERROR", logger="app.audit"), pytest.raises(ServiceUnavailableError):
		await admin_user_service.change_status(_actor(), uuid4(), False, AsyncMock())

	record = caplog.records[-1]
	assert record.operation == "revoke_all_refresh_tokens"


@pytest.mark.asyncio
async def test_change_status_logs_old_is_active_new_is_active_and_redis_counts(
	monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
	target_id = uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=_user(id=target_id, is_active=False)))
	monkeypatch.setattr(admin_repository, "update_user_status", AsyncMock(return_value=True))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(return_value=2))
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", AsyncMock(return_value=3))
	actor = _actor()

	with caplog.at_level("INFO", logger="app.audit"):
		await admin_user_service.change_status(actor, target_id, False, AsyncMock())

	record = caplog.records[-1]
	assert record.old_is_active is True
	assert record.new_is_active is False
	assert record.session_revoked_count == 2
	assert record.refresh_revoked_count == 3


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
async def test_force_logout_idempotent_when_no_active_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(return_value=0))
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", AsyncMock(return_value=0))

	await admin_user_service.force_logout(_actor(), target.id, AsyncMock())


@pytest.mark.asyncio
async def test_force_logout_service_unavailable_on_redis_error(monkeypatch: pytest.MonkeyPatch) -> None:
	target = _user()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(side_effect=RedisConnectionError("redis down")))

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.force_logout(_actor(), target.id, AsyncMock())


@pytest.mark.asyncio
async def test_force_logout_does_not_catch_non_redis_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
	"""設計書§6.4/6.5の送出例外はRedisErrorのみ。プログラミングエラーまで503に化けさせない（#347レビュー対応）。"""
	target = _user()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(side_effect=RuntimeError("bug")))

	with pytest.raises(RuntimeError):
		await admin_user_service.force_logout(_actor(), target.id, AsyncMock())


@pytest.mark.asyncio
async def test_get_existing_user_service_unavailable_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(side_effect=OperationalError("x", {}, Exception())))

	with pytest.raises(ServiceUnavailableError):
		await admin_user_service.force_logout(_actor(), uuid4(), AsyncMock())

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.core.config import get_backend_settings
from app.repository import admin_repository, login_history_repository, project_repository, user_repository
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def _make_admin(db: AsyncSession, username: str) -> uuid.UUID:
	user_id = await user_repository.create(db, username, f"{username}@example.com", "hash")
	await db.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": user_id})
	return user_id


async def test_list_users_filters_by_query_role_and_is_active(db_session: AsyncSession) -> None:
	admin_id = await _make_admin(db_session, "admin-list1")
	member_id = await user_repository.create(db_session, "member-list1", "member-list1@example.com", "hash")
	inactive_id = await user_repository.create(db_session, "inactive-list1", "inactive-list1@example.com", "hash")
	await db_session.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": inactive_id})

	by_query = await admin_repository.list_users(db_session, "member-list1", None, None, 50, 0)
	by_role = await admin_repository.list_users(db_session, None, "admin", None, 50, 0)
	by_active = await admin_repository.list_users(db_session, None, None, False, 50, 0)

	assert {row.user.id for row in by_query} == {member_id}
	assert admin_id in {row.user.id for row in by_role}
	assert member_id not in {row.user.id for row in by_role}
	assert {row.user.id for row in by_active} == {inactive_id}

	# total_countはウィンドウ関数count(*) OVER()で算出される（該当行数と一致するはず）
	assert all(row.total_count == len(by_query) for row in by_query)
	assert all(row.total_count == len(by_active) for row in by_active)


async def test_list_projects_filters_by_query_and_is_active(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "owner-list1", "owner-list1@example.com", "hash")
	active_id = await project_repository.create(db_session, owner_id, "Alpha Project", None, None, None)
	inactive_id = await project_repository.create(db_session, owner_id, "Beta Project", None, None, None)
	await admin_repository.deactivate_project(db_session, inactive_id, False)

	by_query = await admin_repository.list_projects(db_session, "alpha", None, 50, 0)
	by_active = await admin_repository.list_projects(db_session, None, False, 50, 0)

	assert {row.project.id for row in by_query} == {active_id}
	assert {row.project.id for row in by_active} == {inactive_id}

	# total_countはウィンドウ関数count(*) OVER()で算出される（該当行数と一致するはず）
	assert all(row.total_count == len(by_query) for row in by_query)
	assert all(row.total_count == len(by_active) for row in by_active)


async def test_list_login_history_filters_by_user_method_and_success(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "hist-user1", "hist-user1@example.com", "hash")
	other_id = await user_repository.create(db_session, "hist-user2", "hist-user2@example.com", "hash")
	await login_history_repository.create(db_session, user_id, "hist-user1", "session", None, None, True, None)
	await login_history_repository.create(
		db_session, user_id, "hist-user1", "jwt", None, None, False, "invalid_credentials"
	)
	await login_history_repository.create(db_session, other_id, "hist-user2", "session", None, None, True, None)

	by_user = await admin_repository.list_login_history(db_session, user_id, None, None, None, None, None, 50, 0)
	by_method = await admin_repository.list_login_history(db_session, None, None, "jwt", None, None, None, 50, 0)
	by_success = await admin_repository.list_login_history(db_session, None, None, None, False, None, None, 50, 0)
	by_query = await admin_repository.list_login_history(db_session, None, "hist-user2", None, None, None, None, 50, 0)

	assert {row.history.user_id for row in by_user} == {user_id}
	assert len(by_user) == 2
	assert all(row.history.login_method == "jwt" for row in by_method)
	assert all(row.history.success is False for row in by_success)
	assert {row.history.user_id for row in by_query} == {other_id}

	# total_countはウィンドウ関数count(*) OVER()で算出される（該当行数と一致するはず）
	assert all(row.total_count == len(by_user) for row in by_user)
	assert all(row.total_count == len(by_method) for row in by_method)
	assert all(row.total_count == len(by_success) for row in by_success)
	assert all(row.total_count == len(by_query) for row in by_query)


async def test_list_login_history_filters_by_created_at_range(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "hist-range1", "hist-range1@example.com", "hash")
	await login_history_repository.create(db_session, user_id, "hist-range1", "session", None, None, True, None)
	await db_session.execute(
		text(
			"INSERT INTO login_history (user_id, login_identifier, login_method, success, created_at) "
			"VALUES (:user_id, 'hist-range1', 'session', true, now() - interval '10 days')"
		),
		{"user_id": user_id},
	)

	now = datetime.now(timezone.utc)
	boundary = now - timedelta(days=1)
	await db_session.execute(
		text(
			"INSERT INTO login_history "
			"(user_id, login_identifier, login_method, success, created_at) "
			"VALUES (:user_id, 'hist-range1', 'session', true, :created_at)"
		),
		{"user_id": user_id, "created_at": boundary},
	)
	recent_only = await admin_repository.list_login_history(
		db_session, user_id, None, None, None, boundary, None, 50, 0
	)
	old_only = await admin_repository.list_login_history(db_session, user_id, None, None, None, None, boundary, 50, 0)

	assert len(recent_only) == 2
	assert len(old_only) == 1
	assert all(row.history.id != old_only[0].history.id for row in recent_only)

	# total_countはウィンドウ関数count(*) OVER()で算出される（該当行数と一致するはず）
	assert all(row.total_count == len(recent_only) for row in recent_only)
	assert old_only[0].total_count == len(old_only)


async def test_update_user_role_self_modification_raises_p0007(db_session: AsyncSession) -> None:
	admin_id = await _make_admin(db_session, "self-role1")

	with pytest.raises(DBAPIError) as exc_info:
		await admin_repository.update_user_role(db_session, admin_id, admin_id, "member")
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0007"


async def test_update_user_role_last_admin_raises_p0008(db_session: AsyncSession) -> None:
	actor_id = await user_repository.create(db_session, "actor-role1", "actor-role1@example.com", "hash")
	last_admin_id = await _make_admin(db_session, "last-admin-role1")

	with pytest.raises(DBAPIError) as exc_info:
		await admin_repository.update_user_role(db_session, actor_id, last_admin_id, "member")
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0008"


async def test_update_user_role_succeeds_when_another_admin_remains(db_session: AsyncSession) -> None:
	actor_id = await _make_admin(db_session, "actor-role2")
	target_id = await _make_admin(db_session, "target-role2")

	await admin_repository.update_user_role(db_session, actor_id, target_id, "member")

	row = (await db_session.execute(text("SELECT role FROM users WHERE id = :id"), {"id": target_id})).mappings().one()
	assert row["role"] == "member"


async def test_update_user_status_self_modification_raises_p0007(db_session: AsyncSession) -> None:
	admin_id = await _make_admin(db_session, "self-status1")

	with pytest.raises(DBAPIError) as exc_info:
		await admin_repository.update_user_status(db_session, admin_id, admin_id, False)
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0007"


async def test_update_user_status_last_admin_raises_p0008(db_session: AsyncSession) -> None:
	actor_id = await user_repository.create(db_session, "actor-status1", "actor-status1@example.com", "hash")
	last_admin_id = await _make_admin(db_session, "last-admin-status1")

	with pytest.raises(DBAPIError) as exc_info:
		await admin_repository.update_user_status(db_session, actor_id, last_admin_id, False)
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0008"


async def test_update_user_status_succeeds_when_another_admin_remains(db_session: AsyncSession) -> None:
	actor_id = await _make_admin(db_session, "actor-status2")
	target_id = await _make_admin(db_session, "target-status2")

	await admin_repository.update_user_status(db_session, actor_id, target_id, False)

	row = (
		(await db_session.execute(text("SELECT is_active FROM users WHERE id = :id"), {"id": target_id}))
		.mappings()
		.one()
	)
	assert row["is_active"] is False


async def test_deactivate_project_toggles_is_active(db_session: AsyncSession) -> None:
	owner_id = await user_repository.create(db_session, "owner-deact1", "owner-deact1@example.com", "hash")
	project_id = await project_repository.create(db_session, owner_id, "P", None, None, None)

	await admin_repository.deactivate_project(db_session, project_id, False)
	deactivated = await project_repository.get_by_id(db_session, project_id)
	assert deactivated is not None
	assert deactivated.is_active is False

	await admin_repository.deactivate_project(db_session, project_id, True)
	reactivated = await project_repository.get_by_id(db_session, project_id)
	assert reactivated is not None
	assert reactivated.is_active is True


async def test_concurrent_role_demotion_of_two_admins_only_one_succeeds(db_session: AsyncSession) -> None:
	admin_a = await _make_admin(db_session, "concurrent-role-a")
	admin_b = await _make_admin(db_session, "concurrent-role-b")
	actor_id = await user_repository.create(
		db_session, "concurrent-role-actor", "concurrent-role-actor@example.com", "hash"
	)
	await db_session.commit()

	settings = get_backend_settings()
	engine = create_async_engine(settings.database_url)
	session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

	async def _demote(target_id: uuid.UUID) -> str:
		async with session_factory() as session:
			try:
				await admin_repository.update_user_role(session, actor_id, target_id, "member")
				await session.commit()
				return "ok"
			except DBAPIError as exc:
				return getattr(exc.orig, "sqlstate", None) or "unknown_error"

	try:
		results = await asyncio.gather(_demote(admin_a), _demote(admin_b))
	finally:
		await engine.dispose()

	# 有効adminが2人しかいない状態で同時に降格を試みた場合、片方のみ成功しもう片方はP0008で拒否される
	assert sorted(results) == ["P0008", "ok"]

	remaining_admins = (
		(await db_session.execute(text("SELECT count(*) AS c FROM users WHERE role = 'admin' AND is_active = true")))
		.mappings()
		.one()
	)
	assert remaining_admins["c"] == 1

	# 別コネクションでのcommitは本fixtureのrollbackで取り消せないため、後続テストへ有効adminを
	# 残さないよう明示的にクリーンアップしてcommitする
	await db_session.execute(
		text("UPDATE users SET role = 'member' WHERE id IN (:a, :b)"), {"a": admin_a, "b": admin_b}
	)
	await db_session.commit()


async def test_concurrent_status_deactivation_of_two_admins_only_one_succeeds(db_session: AsyncSession) -> None:
	admin_a = await _make_admin(db_session, "concurrent-status-a")
	admin_b = await _make_admin(db_session, "concurrent-status-b")
	actor_id = await user_repository.create(
		db_session, "concurrent-status-actor", "concurrent-status-actor@example.com", "hash"
	)
	await db_session.commit()

	settings = get_backend_settings()
	engine = create_async_engine(settings.database_url)
	session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

	async def _deactivate(target_id: uuid.UUID) -> str:
		async with session_factory() as session:
			try:
				await admin_repository.update_user_status(session, actor_id, target_id, False)
				await session.commit()
				return "ok"
			except DBAPIError as exc:
				return getattr(exc.orig, "sqlstate", None) or "unknown_error"

	try:
		results = await asyncio.gather(_deactivate(admin_a), _deactivate(admin_b))
	finally:
		await engine.dispose()

	# 有効adminが2人しかいない状態で同時に無効化を試みた場合、片方のみ成功しもう片方はP0008で拒否される
	assert sorted(results) == ["P0008", "ok"]

	remaining_admins = (
		(await db_session.execute(text("SELECT count(*) AS c FROM users WHERE role = 'admin' AND is_active = true")))
		.mappings()
		.one()
	)
	assert remaining_admins["c"] == 1

	# 別コネクションでのcommitは本fixtureのrollbackで取り消せないため、後続テストへ有効adminを
	# 残さないよう明示的にクリーンアップしてcommitする
	await db_session.execute(
		text("UPDATE users SET is_active = false WHERE id IN (:a, :b)"), {"a": admin_a, "b": admin_b}
	)
	await db_session.commit()

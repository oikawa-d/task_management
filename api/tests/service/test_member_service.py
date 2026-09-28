"""member_service (プロジェクトメンバーの一覧・追加・削除) のユニットテスト。

repository層をmonkeypatchでスタブ化し、メンバー一覧の整形、既存メンバー・
オーナー除去の拒否、追加/削除失敗時のDBロールバック挙動を検証する。
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import (
	AlreadyMemberError,
	NotFoundError,
	OwnerCannotBeRemovedError,
	ServiceUnavailableError,
)
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.service import member_service
from sqlalchemy.exc import DBAPIError, OperationalError


def _user(username: str = "alice") -> User:
	"""指定ユーザー名でテスト用のUserダミーを生成する。"""
	return User(id=uuid4(), username=username, email=f"{username}@example.com", role="member", is_active=True)


def _project(owner: User) -> Project:
	"""指定ユーザーをオーナーとするテスト用Projectダミーを生成する。"""
	return Project(id=uuid4(), name="Project", owner_id=owner.id, owner=owner, is_active=True)


def _member(project: Project, user: User) -> ProjectMember:
	"""指定プロジェクト・ユーザーの組み合わせでテスト用ProjectMemberダミーを生成する。"""
	return ProjectMember(
		project_id=project.id,
		user_id=user.id,
		user=user,
		joined_at=datetime.now(timezone.utc),
	)


@pytest.mark.asyncio
async def test_list_members_returns_member_summary(monkeypatch: pytest.MonkeyPatch) -> None:
	"""list_by_projectが返すメンバー1件がレスポンスへ正しく整形され、
	総件数・ユーザー名が反映されることを検証する。
	"""
	owner = _user()
	project = _project(owner)
	member = _member(project, _user("bob"))
	list_by_project = AsyncMock(return_value=[member])
	monkeypatch.setattr(member_service.project_member_repository, "list_by_project", list_by_project)

	response = await member_service.list_members(project, AsyncMock())

	assert response.meta.total == 1
	assert response.items[0].username == "bob"


@pytest.mark.asyncio
async def test_add_member_rejects_existing_member(monkeypatch: pytest.MonkeyPatch) -> None:
	"""既にメンバーであるユーザーを追加しようとした場合、AlreadyMemberErrorが送出され、
	DBのcommit・rollbackがどちらも呼ばれないことを検証する。
	"""
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=True))

	db = AsyncMock()
	with pytest.raises(AlreadyMemberError):
		await member_service.add_member(project, target.id, owner.id, db)

	db.rollback.assert_not_awaited()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_member_rejects_missing_user_without_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
	"""追加対象のユーザーIDが存在しない場合、NotFoundErrorが送出され、
	DBのcommit・rollbackがどちらも呼ばれないことを検証する。
	"""
	owner = _user()
	project = _project(owner)
	db = AsyncMock()
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=None))

	with pytest.raises(NotFoundError):
		await member_service.add_member(project, uuid4(), owner.id, db)

	db.rollback.assert_not_awaited()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("database_error", "expected_error"),
	[
		(
			OperationalError("insert member", {}, SimpleNamespace(sqlstate="08006")),
			ServiceUnavailableError,
		),
		(DBAPIError("insert member", {}, Exception("database error")), DBAPIError),
	],
	ids=["connection_error", "other_database_error"],
)
async def test_add_member_rolls_back_database_errors(
	monkeypatch: pytest.MonkeyPatch, database_error: DBAPIError, expected_error: type[Exception]
) -> None:
	"""メンバー作成(create)がDB接続エラー(sqlstate 08006)やその他のDBAPIErrorを
	送出した場合、それぞれServiceUnavailableError・元の例外へ変換され、
	いずれもDBのrollbackが1回呼ばれcommitは呼ばれないことを検証する。
	"""
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	db = AsyncMock()
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=False))
	monkeypatch.setattr(member_service.project_member_repository, "create", AsyncMock(side_effect=database_error))

	with pytest.raises(expected_error):
		await member_service.add_member(project, target.id, owner.id, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_member_rolls_back_not_found_after_create(monkeypatch: pytest.MonkeyPatch) -> None:
	"""メンバー作成後の一覧取得(list_by_project)に追加したはずのメンバーが
	含まれない場合、NotFoundErrorへ変換されDBがrollbackされることを検証する。
	"""
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	db = AsyncMock()
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=False))
	monkeypatch.setattr(member_service.project_member_repository, "create", AsyncMock())
	monkeypatch.setattr(member_service.project_member_repository, "list_by_project", AsyncMock(return_value=[]))

	with pytest.raises(NotFoundError):
		await member_service.add_member(project, target.id, owner.id, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_member_rolls_back_already_member_after_create(monkeypatch: pytest.MonkeyPatch) -> None:
	"""事前のexists確認をすり抜けた後にcreateがAlreadyMemberErrorを送出した場合
	(競合状態を想定)、その例外がそのまま伝播しDBがrollbackされることを検証する。
	"""
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	db = AsyncMock()
	monkeypatch.setattr(member_service.user_repository, "get_by_id", AsyncMock(return_value=target))
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=False))
	monkeypatch.setattr(
		member_service.project_member_repository,
		"create",
		AsyncMock(side_effect=AlreadyMemberError()),
	)

	with pytest.raises(AlreadyMemberError):
		await member_service.add_member(project, target.id, owner.id, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_member_rejects_owner() -> None:
	"""プロジェクトオーナー自身を削除しようとした場合、OwnerCannotBeRemovedErrorが
	送出されることを検証する。
	"""
	owner = _user()
	project = _project(owner)

	with pytest.raises(OwnerCannotBeRemovedError):
		await member_service.remove_member(project, owner.id, AsyncMock())


@pytest.mark.asyncio
async def test_remove_member_rejects_missing_member(monkeypatch: pytest.MonkeyPatch) -> None:
	"""削除対象のユーザーがプロジェクトメンバーとして存在しない場合、
	NotFoundErrorが送出されることを検証する。
	"""
	owner = _user()
	project = _project(owner)
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=False))

	with pytest.raises(NotFoundError):
		await member_service.remove_member(project, uuid4(), AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("database_error", "expected_error"),
	[
		(
			OperationalError("delete member", {}, SimpleNamespace(sqlstate="08006")),
			ServiceUnavailableError,
		),
		(DBAPIError("delete member", {}, Exception("database error")), DBAPIError),
	],
	ids=["connection_error", "other_database_error"],
)
async def test_remove_member_rolls_back_database_errors(
	monkeypatch: pytest.MonkeyPatch, database_error: DBAPIError, expected_error: type[Exception]
) -> None:
	"""メンバー削除(delete)がDB接続エラー(sqlstate 08006)やその他のDBAPIErrorを
	送出した場合、それぞれServiceUnavailableError・元の例外へ変換され、
	いずれもDBのrollbackが1回呼ばれcommitは呼ばれないことを検証する。
	"""
	owner = _user()
	project = _project(owner)
	target = _user("bob")
	db = AsyncMock()
	monkeypatch.setattr(member_service.project_member_repository, "exists", AsyncMock(return_value=True))
	monkeypatch.setattr(member_service.project_member_repository, "delete", AsyncMock(side_effect=database_error))

	with pytest.raises(expected_error):
		await member_service.remove_member(project, target.id, db)

	db.rollback.assert_awaited_once()
	db.commit.assert_not_awaited()

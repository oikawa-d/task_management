"""app.core.deps の認可用依存関数（require_project_member・require_project_owner・require_admin）に対する単体テスト。"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.deps import require_admin, require_project_member, require_project_owner
from app.core.exceptions import ForbiddenError, NotFoundError
from app.schemas.auth import CurrentUser


def _user(*, role: str = "member") -> CurrentUser:
	"""指定したロールを持つ検証用CurrentUserを作る。

	Args:
		role: "member"または"admin"等のロール。

	Returns:
		指定ロールのCurrentUser。
	"""
	return CurrentUser(id=uuid.uuid4(), username="taro", role=role, is_active=True, email_verified_at=None)


def _project(owner_id: uuid.UUID) -> SimpleNamespace:
	"""検証用のプロジェクトを作る。

	Args:
		owner_id: プロジェクトのオーナーとするユーザーID。

	Returns:
		id・owner_id・is_activeを持つSimpleNamespace。
	"""
	return SimpleNamespace(id=uuid.uuid4(), owner_id=owner_id, is_active=True)


class _Db:
	"""require_project_member等へ渡すDBセッションの型を満たすだけのプレースホルダー（実際には使用されない）。"""


async def test_require_project_member_returns_404_when_project_missing(monkeypatch: pytest.MonkeyPatch) -> None:
	"""指定したproject_idに対応するプロジェクトが存在しない場合、メンバー判定（is_member）を
	呼び出す前にNotFoundError（404・NOT_FOUND）を送出することを検証する。
	"""
	monkeypatch.setattr("app.core.deps.project_repository.get_by_id", AsyncMock(return_value=None))
	is_member_mock = AsyncMock(return_value=True)
	monkeypatch.setattr("app.core.deps.project_repository.is_member", is_member_mock)

	with pytest.raises(NotFoundError):
		await require_project_member(uuid.uuid4(), user=_user(), db=_Db())
	is_member_mock.assert_not_awaited()


async def test_require_project_member_returns_404_for_non_member(monkeypatch: pytest.MonkeyPatch) -> None:
	"""プロジェクトは存在するがユーザーがメンバーでない場合、権限不足の存在を推測されないよう
	ForbiddenErrorではなくNotFoundError（404・NOT_FOUND）を送出することを検証する。
	"""
	project = _project(uuid.uuid4())
	monkeypatch.setattr("app.core.deps.project_repository.get_by_id", AsyncMock(return_value=project))
	monkeypatch.setattr("app.core.deps.project_repository.is_member", AsyncMock(return_value=False))

	with pytest.raises(NotFoundError):
		await require_project_member(project.id, user=_user(), db=_Db())


async def test_require_project_member_returns_project_for_member(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ユーザーがプロジェクトのメンバーである場合、例外を送出せずそのプロジェクトを返すことを検証する。"""
	project = _project(uuid.uuid4())
	monkeypatch.setattr("app.core.deps.project_repository.get_by_id", AsyncMock(return_value=project))
	monkeypatch.setattr("app.core.deps.project_repository.is_member", AsyncMock(return_value=True))

	result = await require_project_member(project.id, user=_user(), db=_Db())
	assert result is project


async def test_require_project_member_calls_is_member_even_for_admin(monkeypatch: pytest.MonkeyPatch) -> None:
	"""admin bypassはfn_is_project_member側の戻り値に含まれるため、Python側でroleによる分岐を行わない。"""
	project = _project(uuid.uuid4())
	monkeypatch.setattr("app.core.deps.project_repository.get_by_id", AsyncMock(return_value=project))
	is_member_mock = AsyncMock(return_value=True)
	monkeypatch.setattr("app.core.deps.project_repository.is_member", is_member_mock)

	result = await require_project_member(project.id, user=_user(role="admin"), db=_Db())

	assert result is project
	is_member_mock.assert_awaited_once()


async def test_require_project_owner_allows_owner() -> None:
	"""ユーザーがプロジェクトのオーナー本人である場合、例外を送出せずそのプロジェクトを返すことを検証する。"""
	owner = _user()
	project = _project(owner.id)

	assert await require_project_owner(project=project, user=owner) is project


async def test_require_project_owner_allows_admin_for_non_owned_project() -> None:
	"""adminロールのユーザーは、自身がオーナーでないプロジェクトに対してもrequire_project_ownerを
	通過できる（オーナー限定操作もadminには許可される）ことを検証する。
	"""
	admin = _user(role="admin")
	project = _project(uuid.uuid4())

	assert await require_project_owner(project=project, user=admin) is project


async def test_require_project_owner_rejects_non_owner_member() -> None:
	"""オーナーでもadminでもないmemberロールのユーザーがオーナー限定操作を試みた場合、
	ForbiddenError（403・FORBIDDEN）を送出することを検証する。
	"""
	project = _project(uuid.uuid4())

	with pytest.raises(ForbiddenError):
		await require_project_owner(project=project, user=_user())


def test_require_admin_rejects_member() -> None:
	"""memberロールのユーザーでrequire_adminを呼ぶと、ForbiddenError（403・FORBIDDEN）を送出することを検証する。"""
	with pytest.raises(ForbiddenError):
		require_admin(_user())


def test_require_admin_allows_admin() -> None:
	"""adminロールのユーザーでrequire_adminを呼ぶと、例外を送出せずそのユーザーを返すことを検証する。"""
	admin = _user(role="admin")
	assert require_admin(admin) is admin

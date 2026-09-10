import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.deps import get_comment_for_member, get_task_for_member
from app.core.exceptions import NotFoundError
from app.schemas.auth import CurrentUser


def _user(*, role: str = "member", user_id: uuid.UUID | None = None) -> CurrentUser:
	return CurrentUser(
		id=user_id or uuid.uuid4(), username="taro", role=role, is_active=True, email_verified_at=None
	)


def _task(*, project_id: uuid.UUID | None = None, created_by: uuid.UUID | None = None) -> SimpleNamespace:
	return SimpleNamespace(id=uuid.uuid4(), project_id=project_id, created_by=created_by or uuid.uuid4())


class _Db:
	pass


class TestGetTaskForMember:
	async def test_returns_404_when_task_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr("app.core.deps.task_repository.get_by_id", AsyncMock(return_value=None))

		with pytest.raises(NotFoundError):
			await get_task_for_member(uuid.uuid4(), user=_user(), db=_Db())

	async def test_returns_404_for_non_member_of_project_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
		task = _task(project_id=uuid.uuid4())
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=True)),
		)
		exists = AsyncMock(return_value=False)
		monkeypatch.setattr("app.core.deps.project_member_repository.exists", exists)

		with pytest.raises(NotFoundError):
			await get_task_for_member(task.id, user=_user(), db=_Db())

	async def test_returns_task_for_project_member(self, monkeypatch: pytest.MonkeyPatch) -> None:
		task = _task(project_id=uuid.uuid4())
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=True)),
		)
		monkeypatch.setattr("app.core.deps.project_member_repository.exists", AsyncMock(return_value=True))

		result = await get_task_for_member(task.id, user=_user(), db=_Db())
		assert result is task

	async def test_allows_project_less_task_to_reach_service_for_creator(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""project_idなしタスクは、作成者本人かどうかをdepsでは判定せずserviceの認可へ到達させる。"""
		user = _user()
		task = _task(project_id=None, created_by=user.id)
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=None)),
		)
		exists = AsyncMock()
		monkeypatch.setattr("app.core.deps.project_member_repository.exists", exists)

		result = await get_task_for_member(task.id, user=user, db=_Db())

		assert result is task
		exists.assert_not_awaited()

	async def test_allows_project_less_task_to_reach_service_for_non_creator(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""非作成者であってもdepsでは404にせず、service.require_task_accessへ判定を委ねる。"""
		task = _task(project_id=None)
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=None)),
		)

		result = await get_task_for_member(task.id, user=_user(), db=_Db())
		assert result is task

	async def test_admin_bypasses_project_membership_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
		task = _task(project_id=uuid.uuid4())
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=True)),
		)
		exists = AsyncMock()
		monkeypatch.setattr("app.core.deps.project_member_repository.exists", exists)

		result = await get_task_for_member(task.id, user=_user(role="admin"), db=_Db())

		assert result is task
		exists.assert_not_awaited()


class TestGetCommentForMember:
	def _comment(self, task_id: uuid.UUID) -> SimpleNamespace:
		return SimpleNamespace(id=uuid.uuid4(), task_id=task_id, user_id=uuid.uuid4())

	async def test_returns_404_when_comment_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr("app.core.deps.task_comment_repository.get_by_id", AsyncMock(return_value=None))

		with pytest.raises(NotFoundError):
			await get_comment_for_member(uuid.uuid4(), user=_user(), db=_Db())

	async def test_returns_404_for_non_member_of_project_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
		task = _task(project_id=uuid.uuid4())
		comment = self._comment(task.id)
		monkeypatch.setattr("app.core.deps.task_comment_repository.get_by_id", AsyncMock(return_value=comment))
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=True)),
		)
		monkeypatch.setattr("app.core.deps.project_member_repository.exists", AsyncMock(return_value=False))

		with pytest.raises(NotFoundError):
			await get_comment_for_member(comment.id, user=_user(), db=_Db())

	async def test_allows_project_less_task_comment_to_reach_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""project_idなしタスクへのコメントは、depsでは作成者判定をせずserviceへ到達させる。"""
		task = _task(project_id=None)
		comment = self._comment(task.id)
		monkeypatch.setattr("app.core.deps.task_comment_repository.get_by_id", AsyncMock(return_value=comment))
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=None)),
		)
		exists = AsyncMock()
		monkeypatch.setattr("app.core.deps.project_member_repository.exists", exists)

		result = await get_comment_for_member(comment.id, user=_user(), db=_Db())

		assert result is comment
		assert result.task is task
		exists.assert_not_awaited()

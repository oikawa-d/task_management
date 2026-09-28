"""app.core.deps の get_task_for_member・get_comment_for_member（タスク/コメントの取得と、
メンバーシップ判定をservice層へ委ねる境界）に対する単体テスト。
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.deps import get_comment_for_member, get_task_for_member
from app.core.exceptions import NotFoundError
from app.schemas.auth import CurrentUser


def _user(*, role: str = "member", user_id: uuid.UUID | None = None) -> CurrentUser:
	"""指定したロール・ユーザーIDを持つ検証用CurrentUserを作る。

	Args:
		role: "member"または"admin"等のロール。
		user_id: 指定するユーザーID。Noneの場合は新規生成する。

	Returns:
		指定条件のCurrentUser。
	"""
	return CurrentUser(id=user_id or uuid.uuid4(), username="taro", role=role, is_active=True, email_verified_at=None)


def _task(*, project_id: uuid.UUID | None = None, created_by: uuid.UUID | None = None) -> SimpleNamespace:
	"""検証用のタスクを作る。

	Args:
		project_id: 所属プロジェクトID。Noneの場合はプロジェクト非紐付けタスクを表す。
		created_by: 作成者のユーザーID。Noneの場合は新規生成する。

	Returns:
		id・project_id・created_byを持つSimpleNamespace。
	"""
	return SimpleNamespace(id=uuid.uuid4(), project_id=project_id, created_by=created_by or uuid.uuid4())


class _Db:
	"""get_task_for_member等へ渡すDBセッションの型を満たすだけのプレースホルダー（実際には使用されない）。"""


class TestGetTaskForMember:
	"""get_task_for_member（タスクの存在確認のみを行い、メンバーシップ判定はservice層へ委ねる依存関数）を検証する。"""

	async def test_returns_404_when_task_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""指定したtask_idに対応するタスクが存在しない場合、NotFoundError（404・NOT_FOUND）を送出することを検証する。"""
		monkeypatch.setattr("app.core.deps.task_repository.get_by_id", AsyncMock(return_value=None))

		with pytest.raises(NotFoundError):
			await get_task_for_member(uuid.uuid4(), db=_Db())

	async def test_returns_project_task_without_membership_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""プロジェクト所属タスクが存在する場合、get_task_for_member自体はメンバーシップを判定せず
		タスクをそのまま返す（判定はservice層に委ねる）ことを検証する。
		"""
		task = _task(project_id=uuid.uuid4())
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=True)),
		)
		result = await get_task_for_member(task.id, db=_Db())

		assert result is task

	async def test_returns_task_for_project_member(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""project_is_active=Trueのプロジェクトに所属するタスクを、例外を送出せずそのまま返すことを検証する。"""
		task = _task(project_id=uuid.uuid4())
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=True)),
		)
		result = await get_task_for_member(task.id, db=_Db())
		assert result is task

	async def test_allows_project_less_task_to_reach_service_for_creator(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""project_idなしタスクは、作成者本人かどうかをdepsでは判定せずserviceの認可へ到達させる。"""
		user = _user()
		task = _task(project_id=None, created_by=user.id)
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=None)),
		)
		result = await get_task_for_member(task.id, db=_Db())

		assert result is task

	async def test_allows_project_less_task_to_reach_service_for_non_creator(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""非作成者であってもdepsでは404にせず、service.require_task_accessへ判定を委ねる。"""
		task = _task(project_id=None)
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=None)),
		)

		result = await get_task_for_member(task.id, db=_Db())
		assert result is task

	async def test_project_task_lookup_does_not_check_membership_for_admin(
		self, monkeypatch: pytest.MonkeyPatch
	) -> None:
		"""adminロールに対しても特別な分岐は無く、get_task_for_memberはタスクの存在確認のみを行って
		そのまま返す（メンバーシップ判定自体を行わない）ことを検証する。
		"""
		task = _task(project_id=uuid.uuid4())
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=True)),
		)
		result = await get_task_for_member(task.id, db=_Db())

		assert result is task


class TestGetCommentForMember:
	"""get_comment_for_member（コメントの存在確認と紐づくタスクの読み込みのみを行い、
	メンバーシップ判定はservice層へ委ねる依存関数）を検証する。
	"""

	def _comment(self, task_id: uuid.UUID) -> SimpleNamespace:
		"""検証用のコメントを作る。

		Args:
			task_id: コメントが紐づくタスクのID。

		Returns:
			id・task_id・user_idを持つSimpleNamespace。
		"""
		return SimpleNamespace(id=uuid.uuid4(), task_id=task_id, user_id=uuid.uuid4())

	async def test_returns_404_when_comment_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""指定したcomment_idに対応するコメントが存在しない場合、NotFoundError（404・NOT_FOUND）を送出することを検証する。"""
		monkeypatch.setattr("app.core.deps.task_comment_repository.get_by_id", AsyncMock(return_value=None))

		with pytest.raises(NotFoundError):
			await get_comment_for_member(uuid.uuid4(), db=_Db())

	async def test_returns_comment_without_membership_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""コメントが存在する場合、get_comment_for_memberはメンバーシップを判定せず、
		紐づくタスクをcomment.taskへ読み込んだうえでコメントをそのまま返すことを検証する。
		"""
		task = _task(project_id=uuid.uuid4())
		comment = self._comment(task.id)
		monkeypatch.setattr(
			"app.core.deps.set_committed_value", lambda instance, key, value: setattr(instance, key, value)
		)
		monkeypatch.setattr("app.core.deps.task_comment_repository.get_by_id", AsyncMock(return_value=comment))
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=True)),
		)
		result = await get_comment_for_member(comment.id, db=_Db())

		assert result is comment
		assert result.task is task

	async def test_allows_project_less_task_comment_to_reach_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""project_idなしタスクへのコメントは、depsでは作成者判定をせずserviceへ到達させる。"""
		task = _task(project_id=None)
		comment = self._comment(task.id)
		monkeypatch.setattr(
			"app.core.deps.set_committed_value", lambda instance, key, value: setattr(instance, key, value)
		)
		monkeypatch.setattr("app.core.deps.task_comment_repository.get_by_id", AsyncMock(return_value=comment))
		monkeypatch.setattr(
			"app.core.deps.task_repository.get_by_id",
			AsyncMock(return_value=SimpleNamespace(task=task, project_is_active=None)),
		)
		result = await get_comment_for_member(comment.id, db=_Db())

		assert result is comment
		assert result.task is task

"""task_comment_service のタスクコメントCRUD機能を検証するテストモジュール。

一覧取得・追加・更新・削除について、プロジェクトメンバーシップに基づく権限チェック、非アクティブなタスクの扱い、
DBコミット失敗時のロールバック挙動を、リポジトリと認可サービスをスタブ化した状態で検証する。
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import ForbiddenError, NotFoundError, ServiceUnavailableError
from app.schemas.auth import CurrentUser
from app.schemas.comment import CommentCreateRequest
from app.service import authorization_service, task_comment_service
from sqlalchemy.exc import MultipleResultsFound, OperationalError


def _user(*, role: str = "member") -> CurrentUser:
	"""テスト対象のサービス関数に渡す認証済みユーザー(CurrentUser)を生成する。"""
	return CurrentUser(id=uuid4(), username="taro", role=role, is_active=True, email_verified_at=None)


def _task(user_id, *, project_id=None, is_active: bool = True):
	"""コメント操作の対象となるタスク相当のダミーオブジェクトを生成する。

	created_byにuser_idを設定し、project_idとis_activeで所属プロジェクト・稼働状態を切り替えられるようにする。
	"""
	return SimpleNamespace(id=uuid4(), project_id=project_id, created_by=user_id, is_active=is_active)


def _comment(user_id, task_id):
	"""投稿者情報付きのコメント相当のダミーオブジェクトを生成する。

	author.last_nameに姓を設定し、表示名(display_name)算出のテストに利用できるようにする。
	"""
	now = datetime.now(UTC)
	author = SimpleNamespace(id=user_id, username="taro", last_name="太郎", first_name="")
	return SimpleNamespace(
		id=uuid4(), task_id=task_id, user_id=user_id, body="本文", author=author, created_at=now, updated_at=now
	)


@pytest.mark.asyncio
async def test_list_comments_returns_author_and_count(monkeypatch) -> None:
	"""list_commentsが、取得したコメント件数と、投稿者の表示名(姓)を含むレスポンスを返すことを検証する。"""
	user = _user()
	task = _task(user.id)
	comment = _comment(user.id, task.id)

	monkeypatch.setattr(task_comment_service.task_comment_repository, "list_by_task", AsyncMock(return_value=[comment]))

	response = await task_comment_service.list_comments(task, user, AsyncMock())

	assert response.count == 1
	assert response.items[0].author.display_name == "太郎"


@pytest.mark.asyncio
async def test_list_comments_checks_project_membership_once(monkeypatch) -> None:
	"""list_commentsが、プロジェクトに紐づくタスクに対して、対象ユーザーのプロジェクトメンバーシップ確認を1回だけ行うことを検証する。"""
	user = _user()
	task = _task(uuid4(), project_id=uuid4())
	exists = AsyncMock(return_value=True)
	monkeypatch.setattr(authorization_service.project_member_repository, "exists", exists)
	monkeypatch.setattr(task_comment_service.task_comment_repository, "list_by_task", AsyncMock(return_value=[]))
	db = AsyncMock()

	await task_comment_service.list_comments(task, user, db)

	exists.assert_awaited_once_with(db, task.project_id, user.id)


@pytest.mark.asyncio
async def test_update_comment_rejects_other_member(monkeypatch) -> None:
	"""update_commentが、コメント投稿者本人ではない別メンバーによる更新をForbiddenErrorとして拒否することを検証する。"""
	owner = _user()
	other = _user()
	task = _task(other.id)
	comment = _comment(owner.id, task.id)

	with pytest.raises(ForbiddenError):
		await task_comment_service.update_comment(task, comment, CommentCreateRequest(body="更新"), other, AsyncMock())


@pytest.mark.asyncio
async def test_list_comments_rejects_non_member(monkeypatch) -> None:
	"""list_commentsが、プロジェクトに紐づくタスクに対してプロジェクトメンバーではないユーザーのアクセスをNotFoundErrorとして拒否することを検証する。"""
	user = _user()
	task = SimpleNamespace(id=uuid4(), project_id=uuid4(), created_by=uuid4(), is_active=True)
	exists = AsyncMock(return_value=False)
	monkeypatch.setattr(authorization_service.project_member_repository, "exists", exists)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, user, AsyncMock())


@pytest.mark.asyncio
async def test_list_comments_rejects_inactive_task_for_admin(monkeypatch) -> None:
	"""list_commentsが、管理者ロールであっても非アクティブなタスクへのアクセスをNotFoundErrorとして拒否することを検証する。"""
	admin = _user(role="admin")
	task = _task(uuid4(), is_active=False)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, admin, AsyncMock())


@pytest.mark.asyncio
async def test_list_comments_rejects_inactive_task_for_project_member(monkeypatch) -> None:
	"""list_commentsが、プロジェクトメンバーに対しても非アクティブなタスクをNotFoundErrorとして拒否し、
	メンバーシップ確認自体を行わないことを検証する。
	"""
	user = _user()
	task = _task(uuid4(), project_id=uuid4(), is_active=False)
	exists = AsyncMock(return_value=True)
	monkeypatch.setattr(authorization_service.project_member_repository, "exists", exists)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, user, AsyncMock())
	exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_comments_rejects_inactive_task_for_creator_without_project(monkeypatch) -> None:
	"""list_commentsが、プロジェクト未所属のタスク作成者本人に対しても、非アクティブなタスクをNotFoundErrorとして拒否することを検証する。"""
	user = _user()
	task = _task(user.id, project_id=None, is_active=False)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, user, AsyncMock())


@pytest.mark.asyncio
async def test_add_comment_rejects_inactive_task(monkeypatch) -> None:
	"""add_commentが、非アクティブなタスクへのコメント追加をNotFoundErrorとして拒否することを検証する。"""
	user = _user()
	task = _task(user.id, is_active=False)

	with pytest.raises(NotFoundError):
		await task_comment_service.add_comment(task, CommentCreateRequest(body="本文"), user, AsyncMock())


@pytest.mark.asyncio
async def test_add_comment_fetches_created_comment_by_id(monkeypatch) -> None:
	"""add_commentが、リポジトリのcreateで払い出されたIDでコメントを再取得してレスポンスに反映し、
	一覧取得(list_by_task)は呼び出さないことを検証する。
	"""
	user = _user()
	task = _task(user.id)
	db = AsyncMock()
	comment = _comment(user.id, task.id)
	comment_id = comment.id
	create = AsyncMock(return_value=comment_id)
	get_by_id = AsyncMock(return_value=comment)
	list_by_task = AsyncMock()
	monkeypatch.setattr(task_comment_service.task_comment_repository, "create", create)
	monkeypatch.setattr(task_comment_service.task_comment_repository, "get_by_id", get_by_id)
	monkeypatch.setattr(task_comment_service.task_comment_repository, "list_by_task", list_by_task)

	response = await task_comment_service.add_comment(task, CommentCreateRequest(body="本文"), user, db)

	assert response.id == comment_id
	create.assert_awaited_once_with(db, task.id, user.id, "本文")
	get_by_id.assert_awaited_once_with(db, comment_id)
	list_by_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_comment_converts_database_connection_failure_and_rolls_back(monkeypatch) -> None:
	"""add_commentが、コミット時のDB接続エラー(OperationalError)をServiceUnavailableErrorに変換し、
	ロールバックを行うことを検証する。
	"""
	user = _user()
	task = _task(user.id)
	comment = _comment(user.id, task.id)
	db = AsyncMock()
	db.commit.side_effect = OperationalError("add comment", {}, SimpleNamespace(sqlstate="08006"))
	monkeypatch.setattr(task_comment_service.task_comment_repository, "create", AsyncMock(return_value=comment.id))
	monkeypatch.setattr(task_comment_service.task_comment_repository, "get_by_id", AsyncMock(return_value=comment))

	with pytest.raises(ServiceUnavailableError):
		await task_comment_service.add_comment(task, CommentCreateRequest(body="本文"), user, db)

	db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_add_comment_rolls_back_when_response_construction_fails(monkeypatch) -> None:
	"""add_commentが、コメント作成後のレスポンス組み立て処理で例外が発生した場合でも、
	その例外をそのまま伝播させつつDBロールバックを行うことを検証する。
	"""
	user = _user()
	task = _task(user.id)
	comment = _comment(user.id, task.id)
	db = AsyncMock()
	monkeypatch.setattr(task_comment_service.task_comment_repository, "create", AsyncMock(return_value=comment.id))
	monkeypatch.setattr(task_comment_service.task_comment_repository, "get_by_id", AsyncMock(return_value=comment))

	def raise_response_error(*_args):
		"""レスポンス組み立て(_comment_response)の失敗を模倣し、常にRuntimeErrorを送出するスタブ。"""
		raise RuntimeError("response failed")

	monkeypatch.setattr(task_comment_service, "_comment_response", raise_response_error)

	with pytest.raises(RuntimeError, match="response failed"):
		await task_comment_service.add_comment(task, CommentCreateRequest(body="本文"), user, db)

	db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_add_comment_rolls_back_once_when_created_comment_is_missing(monkeypatch) -> None:
	"""add_commentが、作成直後の再取得でコメントが見つからない場合、NotFoundErrorを送出しつつロールバックを1回だけ行うことを検証する。"""
	user = _user()
	task = _task(user.id)
	db = AsyncMock()
	monkeypatch.setattr(task_comment_service.task_comment_repository, "create", AsyncMock(return_value=uuid4()))
	monkeypatch.setattr(task_comment_service.task_comment_repository, "get_by_id", AsyncMock(return_value=None))

	with pytest.raises(NotFoundError):
		await task_comment_service.add_comment(task, CommentCreateRequest(body="本文"), user, db)

	db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_comment_rejects_inactive_task(monkeypatch) -> None:
	"""update_commentが、非アクティブなタスクに紐づくコメントの更新をNotFoundErrorとして拒否することを検証する。"""
	user = _user()
	task = _task(user.id, is_active=False)
	comment = _comment(user.id, task.id)

	with pytest.raises(NotFoundError):
		await task_comment_service.update_comment(task, comment, CommentCreateRequest(body="更新"), user, AsyncMock())


@pytest.mark.asyncio
async def test_update_comment_rolls_back_when_refetch_returns_multiple_rows(monkeypatch) -> None:
	"""update_commentが、更新後の再取得でMultipleResultsFoundが発生した場合、その例外を伝播させつつロールバックを行うことを検証する。"""
	user = _user()
	task = _task(user.id)
	comment = _comment(user.id, task.id)
	db = AsyncMock()
	monkeypatch.setattr(task_comment_service.task_comment_repository, "update", AsyncMock())
	monkeypatch.setattr(
		task_comment_service.task_comment_repository,
		"get_by_id",
		AsyncMock(side_effect=MultipleResultsFound()),
	)

	with pytest.raises(MultipleResultsFound):
		await task_comment_service.update_comment(task, comment, CommentCreateRequest(body="更新"), user, db)

	db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_comment_rolls_back_once_when_updated_comment_is_missing(monkeypatch) -> None:
	"""update_commentが、更新後の再取得でコメントが見つからない場合、NotFoundErrorを送出しつつロールバックを1回だけ行うことを検証する。"""
	user = _user()
	task = _task(user.id)
	comment = _comment(user.id, task.id)
	db = AsyncMock()
	monkeypatch.setattr(task_comment_service.task_comment_repository, "update", AsyncMock())
	monkeypatch.setattr(task_comment_service.task_comment_repository, "get_by_id", AsyncMock(return_value=None))

	with pytest.raises(NotFoundError):
		await task_comment_service.update_comment(task, comment, CommentCreateRequest(body="更新"), user, db)

	db.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_delete_comment_rejects_inactive_task(monkeypatch) -> None:
	"""delete_commentが、非アクティブなタスクに紐づくコメントの削除をNotFoundErrorとして拒否することを検証する。"""
	user = _user()
	task = _task(user.id, is_active=False)
	comment = _comment(user.id, task.id)

	with pytest.raises(NotFoundError):
		await task_comment_service.delete_comment(task, comment, user, AsyncMock())


@pytest.mark.asyncio
async def test_delete_comment_rolls_back_when_commit_raises_non_database_error(monkeypatch) -> None:
	"""delete_commentが、コミット時にDB接続エラー以外の例外(RuntimeError)が発生した場合でも、
	その例外を変換せずに伝播させつつロールバックを行うことを検証する。
	"""
	user = _user()
	task = _task(user.id)
	comment = _comment(user.id, task.id)
	db = AsyncMock()
	db.commit.side_effect = RuntimeError("commit failed")
	monkeypatch.setattr(task_comment_service.task_comment_repository, "delete", AsyncMock())

	with pytest.raises(RuntimeError, match="commit failed"):
		await task_comment_service.delete_comment(task, comment, user, db)

	db.rollback.assert_awaited_once_with()

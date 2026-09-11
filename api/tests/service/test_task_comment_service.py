from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.core.exceptions import ForbiddenError, NotFoundError
from app.schemas.auth import CurrentUser
from app.schemas.comment import CommentCreateRequest
from app.service import authorization_service, task_comment_service


def _user(*, role: str = "member") -> CurrentUser:
	return CurrentUser(id=uuid4(), username="taro", role=role, is_active=True, email_verified_at=None)


def _task(user_id, *, project_id=None, is_active: bool = True):
	return SimpleNamespace(id=uuid4(), project_id=project_id, created_by=user_id, is_active=is_active)


def _comment(user_id, task_id):
	now = datetime.now(UTC)
	author = SimpleNamespace(id=user_id, username="taro", last_name="太郎", first_name="")
	return SimpleNamespace(
		id=uuid4(), task_id=task_id, user_id=user_id, body="本文", author=author, created_at=now, updated_at=now
	)


@pytest.mark.asyncio
async def test_list_comments_returns_author_and_count(monkeypatch) -> None:
	user = _user()
	task = _task(user.id)
	comment = _comment(user.id, task.id)

	monkeypatch.setattr(task_comment_service.task_comment_repository, "list_by_task", AsyncMock(return_value=[comment]))

	response = await task_comment_service.list_comments(task, user, AsyncMock())

	assert response.count == 1
	assert response.items[0].author.display_name == "太郎"


@pytest.mark.asyncio
async def test_update_comment_rejects_other_member(monkeypatch) -> None:
	owner = _user()
	other = _user()
	task = _task(other.id)
	comment = _comment(owner.id, task.id)

	with pytest.raises(ForbiddenError):
		await task_comment_service.update_comment(task, comment, CommentCreateRequest(body="更新"), other, AsyncMock())


@pytest.mark.asyncio
async def test_list_comments_rejects_non_member(monkeypatch) -> None:
	user = _user()
	task = SimpleNamespace(id=uuid4(), project_id=uuid4(), created_by=uuid4(), is_active=True)
	exists = AsyncMock(return_value=False)
	monkeypatch.setattr(authorization_service.project_member_repository, "exists", exists)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, user, AsyncMock())


@pytest.mark.asyncio
async def test_list_comments_rejects_inactive_task_for_admin(monkeypatch) -> None:
	admin = _user(role="admin")
	task = _task(uuid4(), is_active=False)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, admin, AsyncMock())


@pytest.mark.asyncio
async def test_list_comments_rejects_inactive_task_for_project_member(monkeypatch) -> None:
	user = _user()
	task = _task(uuid4(), project_id=uuid4(), is_active=False)
	exists = AsyncMock(return_value=True)
	monkeypatch.setattr(authorization_service.project_member_repository, "exists", exists)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, user, AsyncMock())
	exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_comments_rejects_inactive_task_for_creator_without_project(monkeypatch) -> None:
	user = _user()
	task = _task(user.id, project_id=None, is_active=False)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, user, AsyncMock())


@pytest.mark.asyncio
async def test_add_comment_rejects_inactive_task(monkeypatch) -> None:
	user = _user()
	task = _task(user.id, is_active=False)

	with pytest.raises(NotFoundError):
		await task_comment_service.add_comment(task, CommentCreateRequest(body="本文"), user, AsyncMock())


@pytest.mark.asyncio
async def test_add_comment_fetches_created_comment_by_id(monkeypatch) -> None:
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
async def test_update_comment_rejects_inactive_task(monkeypatch) -> None:
	user = _user()
	task = _task(user.id, is_active=False)
	comment = _comment(user.id, task.id)

	with pytest.raises(NotFoundError):
		await task_comment_service.update_comment(task, comment, CommentCreateRequest(body="更新"), user, AsyncMock())


@pytest.mark.asyncio
async def test_delete_comment_rejects_inactive_task(monkeypatch) -> None:
	user = _user()
	task = _task(user.id, is_active=False)
	comment = _comment(user.id, task.id)

	with pytest.raises(NotFoundError):
		await task_comment_service.delete_comment(task, comment, user, AsyncMock())

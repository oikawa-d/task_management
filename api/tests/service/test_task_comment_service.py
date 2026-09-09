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


def _task(user_id):
	return SimpleNamespace(id=uuid4(), project_id=None, created_by=user_id)


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
	task = SimpleNamespace(id=uuid4(), project_id=uuid4(), created_by=uuid4())
	exists = AsyncMock(return_value=False)
	monkeypatch.setattr(authorization_service.project_member_repository, "exists", exists)

	with pytest.raises(NotFoundError):
		await task_comment_service.list_comments(task, user, AsyncMock())

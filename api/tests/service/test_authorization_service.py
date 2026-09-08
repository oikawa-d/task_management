import uuid
from types import SimpleNamespace

import pytest
from app.core.exceptions import ForbiddenError, NotFoundError, UserInactiveError
from app.service.authorization_service import (
	CurrentUser,
	assert_comment_editable,
	authorize_project_member,
	authorize_project_owner,
	authorize_task_access,
)


def _user(*, role: str = "member", active: bool = True) -> CurrentUser:
	return CurrentUser(id=uuid.uuid4(), username="user", role=role, is_active=active)


def _project(owner_id: uuid.UUID, *, active: bool = True) -> SimpleNamespace:
	return SimpleNamespace(id=uuid.uuid4(), owner_id=owner_id, is_active=active)


def test_authorize_project_member_allows_admin_without_membership() -> None:
	user = _user(role="admin")
	project = _project(uuid.uuid4())

	assert authorize_project_member(user, project, is_member=False) is project


def test_authorize_project_member_hides_inactive_project() -> None:
	user = _user()
	project = _project(user.id, active=False)

	with pytest.raises(NotFoundError):
		authorize_project_member(user, project, is_member=True)


def test_authorize_project_member_hides_non_membership_as_not_found() -> None:
	user = _user()
	project = _project(uuid.uuid4())

	with pytest.raises(NotFoundError):
		authorize_project_member(user, project, is_member=False)


def test_authorize_project_member_rejects_inactive_user() -> None:
	user = _user(active=False)
	project = _project(user.id)

	with pytest.raises(UserInactiveError):
		authorize_project_member(user, project, is_member=True)


def test_authorize_project_owner_allows_owner_and_admin() -> None:
	owner = _user()
	project = _project(owner.id)
	admin = _user(role="admin")

	assert authorize_project_owner(owner, project, is_member=True) is project
	assert authorize_project_owner(admin, project, is_member=False) is project


def test_authorize_project_owner_rejects_member_who_is_not_owner() -> None:
	user = _user()
	project = _project(uuid.uuid4())

	with pytest.raises(ForbiddenError):
		authorize_project_owner(user, project, is_member=True)


def test_authorize_task_access_hides_inactive_or_unassigned_task() -> None:
	user = _user()
	inactive_task = SimpleNamespace(id=uuid.uuid4(), project_id=uuid.uuid4(), created_by=user.id, is_active=False)

	with pytest.raises(NotFoundError):
		authorize_task_access(user, inactive_task, is_member=True)


def test_assert_comment_editable_allows_author_and_admin_only() -> None:
	user = _user()
	comment = SimpleNamespace(user_id=user.id)

	assert_comment_editable(comment, user)
	assert_comment_editable(comment, _user(role="admin"))

	with pytest.raises(ForbiddenError):
		assert_comment_editable(comment, _user())

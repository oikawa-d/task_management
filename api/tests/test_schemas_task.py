from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.schemas.task import (
	BoardResponse,
	TaskCreateFlatRequest,
	TaskCreateRequest,
	TaskDetailResponse,
	TaskListQuery,
	TaskListResponse,
	TaskResponse,
	TaskSummary,
	TaskUpdateRequest,
)
from pydantic import ValidationError


def test_task_create_request_applies_defaults() -> None:
	payload = TaskCreateRequest(title="タスク")

	assert payload.description is None
	assert payload.status == "todo"
	assert payload.assignee_id is None
	assert payload.due_at is None


@pytest.mark.parametrize("title", ["", "a" * 151])
def test_task_create_request_rejects_invalid_title(title: str) -> None:
	with pytest.raises(ValidationError):
		TaskCreateRequest(title=title)


def test_task_create_request_rejects_unknown_position() -> None:
	with pytest.raises(ValidationError):
		TaskCreateRequest(title="タスク", position=0)


def test_task_create_request_accepts_task_fields() -> None:
	assignee_id = uuid4()
	due_at = datetime(2026, 9, 3, 4, 5, tzinfo=timezone.utc)

	payload = TaskCreateRequest(
		title="タスク",
		description="説明",
		status="in_progress",
		assignee_id=assignee_id,
		due_at=due_at,
	)

	assert payload.assignee_id == assignee_id
	assert payload.due_at == due_at


def test_task_create_flat_request_rejects_assignee_without_project() -> None:
	with pytest.raises(ValidationError):
		TaskCreateFlatRequest(title="個人タスク", assignee_id=uuid4())


def test_task_create_flat_request_normalizes_explicit_null_project() -> None:
	payload = TaskCreateFlatRequest(project_id=None, title="個人タスク")

	assert payload.project_id is None


def test_task_update_request_requires_version_and_preserves_unset_fields() -> None:
	payload = TaskUpdateRequest(version=2, description=None)

	assert payload.model_dump(exclude_unset=True) == {"version": 2, "description": None}


def test_task_update_request_validates_partial_fields() -> None:
	payload = TaskUpdateRequest(version=1, title="更新", position=0, is_active=False)

	assert payload.title == "更新"
	assert payload.position == 0
	assert payload.is_active is False


@pytest.mark.parametrize(
	"payload",
	[
		{"version": 1, "title": ""},
		{"version": 1, "title": "a" * 151},
		{"version": 1, "description": "a" * 2001},
		{"version": 1, "position": -1},
		{"version": 1, "title": None},
		{"version": 1, "status": None},
		{"version": 1, "position": None},
		{"version": 1, "is_active": None},
		{"version": 1, "project_id": str(uuid4())},
	],
)
def test_task_update_request_rejects_invalid_fields(payload: dict[str, object]) -> None:
	with pytest.raises(ValidationError):
		TaskUpdateRequest(**payload)


def test_task_list_query_applies_defaults() -> None:
	query = TaskListQuery()

	assert query.page == 1
	assert query.per_page == 20
	assert query.project_id is None
	assert query.status is None
	assert query.include_inactive is False
	assert query.sort == "created_at"
	assert query.order == "desc"


def test_task_list_query_normalizes_null_project_filter() -> None:
	query = TaskListQuery(project_id="null")

	assert query.project_id == "unassigned"


@pytest.mark.parametrize(
	"payload",
	[
		{"page": 0},
		{"per_page": 0},
		{"per_page": 101},
		{"project_id": "not-a-uuid"},
		{"status": "invalid"},
		{"sort": "position"},
		{"order": "random"},
		{"project_id": "unassigned"},
	],
)
def test_task_list_query_rejects_invalid_filters(payload: dict[str, object]) -> None:
	with pytest.raises(ValidationError):
		TaskListQuery(**payload)


def test_task_response_and_detail_response_validate_task_output() -> None:
	user_id = uuid4()
	base = {
		"id": uuid4(),
		"project_id": uuid4(),
		"project_is_active": True,
		"title": "タスク",
		"description": None,
		"status": "todo",
		"assignee": {"id": user_id, "username": "taro", "display_name": "山田 太郎"},
		"created_by": {"id": user_id, "username": "taro"},
		"position": 0,
		"version": 1,
		"is_active": True,
		"due_at": None,
		"created_at": datetime.now(timezone.utc),
		"updated_at": datetime.now(timezone.utc),
	}

	response = TaskResponse.model_validate(base)
	detail = TaskDetailResponse.model_validate({**base, "comment_count": 2})

	assert response.project_id == base["project_id"]
	assert response.created_by.display_name is None
	assert detail.comment_count == 2


def test_task_summary_and_board_response_validate_board_output() -> None:
	task = TaskSummary(
		id=uuid4(),
		title="タスク",
		description=None,
		assignee=None,
		due_at=None,
		position=0,
		version=1,
		is_active=True,
		comment_count=0,
		created_at=datetime.now(timezone.utc),
		updated_at=datetime.now(timezone.utc),
	)
	board = BoardResponse(project_id=uuid4(), project_is_active=True, columns={"todo": [task]})

	assert board.columns.todo == [task]
	assert board.columns.in_progress == []
	assert board.columns.done == []


def test_task_list_response_validates_pagination_meta() -> None:
	response = TaskListResponse(items=[], meta={"page": 2, "per_page": 20, "total": 21, "total_pages": 2})

	assert response.meta.total_pages == 2

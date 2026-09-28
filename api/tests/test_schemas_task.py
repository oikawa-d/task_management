"""
タスクスキーマの作成・更新・リスト・カレンダークエリ・出力のバリデーションを検証するテスト。
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.schemas.task import (
	BoardResponse,
	CalendarTaskQuery,
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
	"""
	TaskCreateRequest がデフォルト値（description=None、status="todo"、assignee_id=None、due_at=None）を適用することを検証。

	条件：title のみを指定してTaskCreateRequest を作成したとき、各フィールドがデフォルト値を持つこと。
	"""
	payload = TaskCreateRequest(title="タスク")

	assert payload.description is None
	assert payload.status == "todo"
	assert payload.assignee_id is None
	assert payload.due_at is None


@pytest.mark.parametrize("title", ["", "a" * 151])
def test_task_create_request_rejects_invalid_title(title: str) -> None:
	"""
	TaskCreateRequest が不正な title（空、151文字超）を拒否することを検証。

	条件：title が空または151文字超のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		TaskCreateRequest(title=title)


def test_task_create_request_rejects_unknown_position() -> None:
	"""
	TaskCreateRequest が unknown position（例：0）を拒否することを検証。

	条件：position=0 を指定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		TaskCreateRequest(title="タスク", position=0)


def test_task_create_request_accepts_task_fields() -> None:
	"""
	TaskCreateRequest が task フィールド（description、status、assignee_id、due_at）を受け入れることを検証。

	条件：すべてのフィールドを指定してTaskCreateRequest を作成したとき、各フィールドが正しく保持されること。
	"""
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


@pytest.mark.parametrize("model", [TaskCreateRequest, TaskCreateFlatRequest])
def test_task_create_description_accepts_boundary_and_rejects_over_limit(model: type[object]) -> None:
	"""
	TaskCreateRequest と TaskCreateFlatRequest が description の2000文字上限を検証することを検証。

	条件：description が2000文字のとき成功し、2001文字以上のときに ValidationError が送出されること。
	"""
	assert model(title="task", description="a" * 2000)
	with pytest.raises(ValidationError):
		model(title="task", description="a" * 2001)


def test_task_create_flat_request_rejects_assignee_without_project() -> None:
	"""
	TaskCreateFlatRequest が project なしで assignee_id を拒否することを検証。

	条件：project_id を指定せず assignee_id のみ指定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		TaskCreateFlatRequest(title="個人タスク", assignee_id=uuid4())


def test_task_create_flat_request_normalizes_explicit_null_project() -> None:
	"""
	TaskCreateFlatRequest が明示的な null project を正規化することを検証。

	条件：project_id=None を明示的に指定したとき、project_id が None に保たれること。
	"""
	payload = TaskCreateFlatRequest(project_id=None, title="個人タスク")

	assert payload.project_id is None


def test_task_update_request_requires_version_and_preserves_unset_fields() -> None:
	"""
	TaskUpdateRequest が version を必須とし、unset フィールドを preserveすることを検証。

	条件：version と description=None を指定してTaskUpdateRequest を作成したとき、model_dump(exclude_unset=True) で {"version": 2, "description": None} が返されること。
	"""
	payload = TaskUpdateRequest(version=2, description=None)

	assert payload.model_dump(exclude_unset=True) == {"version": 2, "description": None}


def test_task_update_request_validates_partial_fields() -> None:
	"""
	TaskUpdateRequest が部分的なフィールド更新をバリデーションすることを検証。

	条件：version 付きで title、position、is_active などの部分フィールドを指定したとき、各フィールドが正しく保持されること。
	"""
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
	"""
	TaskUpdateRequest が不正なフィールド値（空、長すぎる、negative、null on non-nullable、文字列の UUID）を拒否することを検証。

	条件：各パターンの不正値を指定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		TaskUpdateRequest(**payload)


def test_task_list_query_applies_defaults() -> None:
	"""
	TaskListQuery がドキュメント化されたデフォルト値（page=1、per_page=20、status=None、sort="created_at"、order="desc"）を適用することを検証。

	条件：パラメータ指定なしでTaskListQuery を作成したとき、各フィールドがデフォルト値を持つこと。
	"""
	query = TaskListQuery()

	assert query.page == 1
	assert query.per_page == 20
	assert query.project_id is None
	assert query.status is None
	assert query.include_inactive is False
	assert query.sort == "created_at"
	assert query.order == "desc"


def test_calendar_task_query_accepts_date_alias_and_project_scope() -> None:
	"""
	CalendarTaskQuery が date エイリアス（from→from_date、to→to_date）と scope="project" を受け入れることを検証。

	条件：from/to エイリアスと scope="project" を指定したとき、from_date/to_date に変換され、project_id が正しく保持されること。
	"""
	project_id = uuid4()
	query = CalendarTaskQuery(
		**{"from": "2026-09-01", "to": "2026-09-30", "scope": "project", "project_id": project_id}
	)

	assert query.from_date.isoformat() == "2026-09-01"
	assert query.to_date.isoformat() == "2026-09-30"
	assert query.project_id == project_id


@pytest.mark.parametrize(
	"payload",
	[
		{"from": "2026-09-01", "to": "2026-11-03", "scope": "me"},
		{"from": "2026-09-02", "to": "2026-09-01", "scope": "me"},
		{"from": "2026-09-01", "to": "2026-09-02", "scope": "project"},
		{"from": "2026-09-01", "to": "2026-09-02", "scope": "me", "project_id": str(uuid4())},
	],
)
def test_calendar_task_query_rejects_invalid_range_or_scope(payload: dict[str, object]) -> None:
	"""
	CalendarTaskQuery が不正な期間または scope の組み合わせを拒否することを検証。

	条件：期間が91日超、from > to、scope="project" で project_id 無しまたは scope="me" で project_id 指定など、不正な組み合わせのとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		CalendarTaskQuery(**payload)


def test_task_list_query_normalizes_null_project_filter() -> None:
	"""
	TaskListQuery が project_id="null" を "unassigned" に正規化することを検証。

	条件：project_id="null" を指定したとき、project_id が "unassigned" に変換されること。
	"""
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
	"""
	TaskListQuery が不正なフィルタパラメータ（page=0、per_page=0/101超、invalid project_id/status/sort/order）を拒否することを検証。

	条件：各パターンの不正フィルタを指定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		TaskListQuery(**payload)


def test_task_response_and_detail_response_validate_task_output() -> None:
	"""
	TaskResponse と TaskDetailResponse が nested タスク出力（assignee、created_by）をバリデーションすることを検証。

	条件：TaskResponse と TaskDetailResponse を model_validate で作成したとき、nested オブジェクトが正しくバリデーションされ、comment_count が保持されること。
	"""
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
	"""
	TaskSummary と BoardResponse がボード出力（columns: todo、in_progress、done）をバリデーションすることを検証。

	条件：TaskSummary をタスク、BoardResponse のcolumns に{"todo": [task]} を指定したとき、各カラム（in_progress、done）がデフォルト空リストを持つこと。
	"""
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
	"""
	TaskListResponse が pagination meta（page、per_page、total、total_pages）をバリデーションすることを検証。

	条件：items と meta を指定してTaskListResponse を作成したとき、meta.total_pages が正しく保持されること。
	"""
	response = TaskListResponse(items=[], meta={"page": 2, "per_page": 20, "total": 21, "total_pages": 2})

	assert response.meta.total_pages == 2

"""
プロジェクトスキーマのクエリ・作成・更新リクエスト・レスポンスのバリデーションを検証するテスト。
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.schemas.project import (
	ProjectCreateRequest,
	ProjectDetailResponse,
	ProjectListMeta,
	ProjectListQuery,
	ProjectListResponse,
	ProjectMember,
	ProjectOwner,
	ProjectPathParams,
	ProjectSummaryResponse,
	ProjectTaskCounts,
	ProjectUpdateRequest,
)
from pydantic import ValidationError


def test_project_list_query_uses_documented_defaults() -> None:
	"""
	ProjectListQuery がドキュメント化されたデフォルト値（page=1、per_page=20、include_inactive=False）を使用することを検証。

	条件：パラメータ指定なしでProjectListQuery を作成したとき、各フィールドがデフォルト値を持つこと。
	"""
	query = ProjectListQuery()

	assert query.page == 1
	assert query.per_page == 20
	assert query.include_inactive is False


@pytest.mark.parametrize("field, value", [("page", 0), ("per_page", 0), ("per_page", 101)])
def test_project_list_query_rejects_out_of_range_values(field: str, value: int) -> None:
	"""
	ProjectListQuery が範囲外のクエリパラメータ（page=0、per_page=0または101以上）を拒否することを検証。

	条件：page またはper_page が許可範囲外のときに、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		ProjectListQuery(**{field: value})


def test_project_create_request_accepts_optional_fields_and_equal_period() -> None:
	"""
	ProjectCreateRequest がオプショナルフィールド（description）と start_at == end_at の期間を受け入れることを検証。

	条件：name、start_at=end_at（同一日時）を指定し、description は省略したとき、description が None に保たれ、期間が正しく保持されること。
	"""
	period = datetime(2026, 9, 1, tzinfo=timezone.utc)

	payload = ProjectCreateRequest(name="Cerberus", start_at=period, end_at=period)

	assert payload.description is None
	assert payload.start_at == period
	assert payload.end_at == period


def test_project_create_request_rejects_end_before_start() -> None:
	"""
	ProjectCreateRequest が end_at < start_at（逆順期間）を拒否することを検証。

	条件：start_at が end_at より後の日時のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		ProjectCreateRequest(
			name="Cerberus",
			start_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
			end_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
		)


@pytest.mark.parametrize("name", ["", "a" * 101])
def test_project_create_request_rejects_invalid_name_length(name: str) -> None:
	"""
	ProjectCreateRequest が不正な name 長（空、101文字超）を拒否することを検証。

	条件：name が空または101文字超のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		ProjectCreateRequest(name=name)


@pytest.mark.parametrize("model", [ProjectCreateRequest, ProjectUpdateRequest])
def test_project_description_accepts_boundary_and_rejects_over_limit(model: type[object]) -> None:
	"""
	ProjectCreateRequest と ProjectUpdateRequest が description の2000文字上限を検証することを検証。

	条件：description が2000文字のとき成功し、2001文字以上のときに ValidationError が送出されること。
	"""
	assert model(description="a" * 2000, **({"name": "project"} if model is ProjectCreateRequest else {}))
	with pytest.raises(ValidationError):
		model(description="a" * 2001, **({"name": "project"} if model is ProjectCreateRequest else {}))


def test_project_update_request_requires_at_least_one_field() -> None:
	"""
	ProjectUpdateRequest が最低1つのフィールドを必須とすることを検証。

	条件：フィールド指定なしでProjectUpdateRequest を作成したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		ProjectUpdateRequest()


def test_project_update_request_distinguishes_explicit_null_from_unset() -> None:
	"""
	ProjectUpdateRequest が明示的な null と未設定フィールドを区別することを検証。

	条件：description=None を明示的に指定したとき、model_fields_set に "description" が含まれ、model_dump(exclude_unset=True) で {"description": None} が返されること。
	"""
	payload = ProjectUpdateRequest(description=None)

	assert payload.model_fields_set == {"description"}
	assert payload.model_dump(exclude_unset=True) == {"description": None}


@pytest.mark.parametrize("field", ["name", "is_active"])
def test_project_update_request_rejects_null_for_non_nullable_fields(field: str) -> None:
	"""
	ProjectUpdateRequest が non-nullable フィールド（name、is_active）への null を拒否することを検証。

	条件：name または is_active に None を設定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		ProjectUpdateRequest(**{field: None})


def test_project_path_params_parses_uuid() -> None:
	"""
	ProjectPathParams が project_id（UUID）をパースすることを検証。

	条件：UUID を指定してProjectPathParams を作成したとき、project_id が正しくパースされること。
	"""
	project_id = uuid4()

	params = ProjectPathParams(project_id=project_id)

	assert params.project_id == project_id


def test_project_path_params_rejects_invalid_uuid() -> None:
	"""
	ProjectPathParams が不正な UUID 形式を拒否することを検証。

	条件：UUID でない文字列を project_id に設定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		ProjectPathParams(project_id="not-a-uuid")


def test_project_response_schemas_validate_nested_crud_response() -> None:
	"""
	ProjectResponseスキーマ（Summary、Detail、List）が nested オブジェクト（owner、members、counts）を含む CRUD response を検証することを検証。

	条件：ProjectSummaryResponse と ProjectDetailResponse を組み立てたとき、nested フィールドが正しくバリデーションされ、ProjectListResponse に含まれたとき UUID 型が保持されること。
	"""
	project_id = uuid4()
	owner_id = uuid4()
	created_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
	owner = ProjectOwner(id=owner_id, username="taro", display_name="山田 太郎")
	counts = ProjectTaskCounts(todo=1, in_progress=2, done=3)
	summary = ProjectSummaryResponse(
		id=project_id,
		name="Cerberus",
		description=None,
		owner=owner,
		member_count=1,
		task_counts=counts,
		is_owner=True,
		is_active=True,
		start_at=None,
		end_at=None,
		created_at=created_at,
	)
	member = ProjectMember(
		user_id=owner_id,
		username="taro",
		display_name="山田 太郎",
		is_owner=True,
		joined_at=created_at,
	)
	detail = ProjectDetailResponse(
		**summary.model_dump(exclude={"updated_at"}),
		updated_at=created_at,
		members=[member],
	)
	response = ProjectListResponse(
		items=[summary],
		meta=ProjectListMeta(page=1, per_page=20, total=1, total_pages=1),
	)

	assert detail.members[0].user_id == owner_id
	assert detail.updated_at == created_at
	assert response.items[0].id == project_id
	assert isinstance(response.items[0].id, UUID)

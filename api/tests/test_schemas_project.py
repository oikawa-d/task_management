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
	query = ProjectListQuery()

	assert query.page == 1
	assert query.per_page == 20
	assert query.include_inactive is False


@pytest.mark.parametrize("field, value", [("page", 0), ("per_page", 0), ("per_page", 101)])
def test_project_list_query_rejects_out_of_range_values(field: str, value: int) -> None:
	with pytest.raises(ValidationError):
		ProjectListQuery(**{field: value})


def test_project_create_request_accepts_optional_fields_and_equal_period() -> None:
	period = datetime(2026, 9, 1, tzinfo=timezone.utc)

	payload = ProjectCreateRequest(name="Cerberus", start_at=period, end_at=period)

	assert payload.description is None
	assert payload.start_at == period
	assert payload.end_at == period


def test_project_create_request_rejects_end_before_start() -> None:
	with pytest.raises(ValidationError):
		ProjectCreateRequest(
			name="Cerberus",
			start_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
			end_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
		)


@pytest.mark.parametrize("name", ["", "a" * 101])
def test_project_create_request_rejects_invalid_name_length(name: str) -> None:
	with pytest.raises(ValidationError):
		ProjectCreateRequest(name=name)


def test_project_update_request_requires_at_least_one_field() -> None:
	with pytest.raises(ValidationError):
		ProjectUpdateRequest()


def test_project_update_request_distinguishes_explicit_null_from_unset() -> None:
	payload = ProjectUpdateRequest(description=None)

	assert payload.model_fields_set == {"description"}
	assert payload.model_dump(exclude_unset=True) == {"description": None}


@pytest.mark.parametrize("field", ["name", "is_active"])
def test_project_update_request_rejects_null_for_non_nullable_fields(field: str) -> None:
	with pytest.raises(ValidationError):
		ProjectUpdateRequest(**{field: None})


def test_project_path_params_parses_uuid() -> None:
	project_id = uuid4()

	params = ProjectPathParams(project_id=project_id)

	assert params.project_id == project_id


def test_project_path_params_rejects_invalid_uuid() -> None:
	with pytest.raises(ValidationError):
		ProjectPathParams(project_id="not-a-uuid")


def test_project_response_schemas_validate_nested_crud_response() -> None:
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

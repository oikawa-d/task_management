from datetime import datetime, timezone
from uuid import UUID, uuid1, uuid4

import pytest
from app.schemas.project_member import (
	AddMemberRequest,
	CandidateListResponse,
	CandidateSearchQuery,
	CandidateSummary,
	MemberDeletePathParams,
	MemberListMeta,
	MemberListQueryParams,
	MemberListResponse,
	MemberResponse,
	MemberSummary,
)
from pydantic import ValidationError


def test_member_list_query_params_accepts_uuid4() -> None:
	project_id = uuid4()

	params = MemberListQueryParams(project_id=project_id)

	assert params.project_id == project_id
	assert isinstance(params.project_id, UUID)


def test_member_delete_path_params_requires_two_uuid4_values() -> None:
	project_id = uuid4()
	user_id = uuid4()

	params = MemberDeletePathParams(project_id=project_id, user_id=user_id)

	assert params.project_id == project_id
	assert params.user_id == user_id


@pytest.mark.parametrize(
	"schema, payload",
	[
		(MemberListQueryParams, {"project_id": "not-a-uuid"}),
		(MemberDeletePathParams, {"project_id": uuid4(), "user_id": "not-a-uuid"}),
	],
)
def test_member_path_params_reject_invalid_uuid(schema: type[object], payload: dict[str, object]) -> None:
	with pytest.raises(ValidationError):
		schema(**payload)  # type: ignore[call-arg]


def test_member_response_accepts_nullable_display_name_and_user_role() -> None:
	joined_at = datetime(2026, 9, 3, 4, 5, tzinfo=timezone.utc)

	response = MemberResponse(
		user_id=uuid4(),
		username="hanako",
		display_name=None,
		role="member",
		is_owner=False,
		is_active=True,
		joined_at=joined_at,
	)

	assert response.display_name is None
	assert response.role == "member"
	assert response.joined_at == joined_at


def test_member_summary_rejects_unknown_role() -> None:
	with pytest.raises(ValidationError):
		MemberSummary(
			user_id=uuid4(),
			username="hanako",
			display_name="鈴木 花子",
			role="owner",
			is_owner=False,
			is_active=True,
			joined_at=datetime.now(timezone.utc),
		)


def test_member_list_response_contains_items_and_non_negative_total() -> None:
	member = MemberSummary(
		user_id=uuid4(),
		username="taro",
		display_name="山田 太郎",
		role="admin",
		is_owner=True,
		is_active=True,
		joined_at=datetime.now(timezone.utc),
	)

	response = MemberListResponse(items=[member], meta=MemberListMeta(total=1))

	assert response.items[0] == member
	assert response.meta.total == 1


def test_member_list_meta_rejects_negative_total() -> None:
	with pytest.raises(ValidationError):
		MemberListMeta(total=-1)


@pytest.mark.parametrize("user_id", ["not-a-uuid", uuid1()])
def test_add_member_request_requires_uuid4(user_id: object) -> None:
	with pytest.raises(ValidationError):
		AddMemberRequest(user_id=user_id)


def test_candidate_search_query_accepts_boundary_lengths() -> None:
	assert CandidateSearchQuery(q="a").q == "a"
	assert CandidateSearchQuery(q="a" * 50).q == "a" * 50


@pytest.mark.parametrize("query", ["", "a" * 51])
def test_candidate_search_query_rejects_out_of_range_length(query: str) -> None:
	with pytest.raises(ValidationError):
		CandidateSearchQuery(q=query)


def test_candidate_list_response_contains_only_non_email_candidate_fields() -> None:
	candidate = CandidateSummary(user_id=uuid4(), username="hanako", display_name="鈴木 花子")
	response = CandidateListResponse(items=[candidate])

	assert response.items[0] == candidate
	assert "email" not in response.model_dump()

"""
プロジェクトメンバースキーマのパスパラメータ・リスト・候補検索のバリデーションを検証するテスト。
"""

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
	"""
	MemberListQueryParams が project_id（UUID4）を受け入れることを検証。

	条件：UUID4 を指定してMemberListQueryParams を作成したとき、project_id が UUID 型として正しくパースされること。
	"""
	project_id = uuid4()

	params = MemberListQueryParams(project_id=project_id)

	assert params.project_id == project_id
	assert isinstance(params.project_id, UUID)


def test_member_delete_path_params_requires_two_uuid4_values() -> None:
	"""
	MemberDeletePathParams が project_id と user_id（両者UUID4）を要求することを検証。

	条件：両者の UUID4 を指定してMemberDeletePathParams を作成したとき、各フィールドが正しくパースされること。
	"""
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
	"""
	MemberListQueryParams と MemberDeletePathParams が invalid UUID を拒否することを検証。

	条件：UUID でない文字列を project_id または user_id に設定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		schema(**payload)  # type: ignore[call-arg]


def test_member_response_accepts_nullable_display_name_and_user_role() -> None:
	"""
	MemberResponse が nullable display_name と user role（"member"など）を受け入れることを検証。

	条件：display_name=None、role="member" を指定してMemberResponse を作成したとき、各フィールドが正しく保持されること。
	"""
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
	"""
	MemberSummary が unknown role（例："owner"）を拒否することを検証。

	条件：role="owner"（MemberSummary では未許可）を指定したとき、ValidationError が送出されること。
	"""
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
	"""
	MemberListResponse が items と non-negative total を含むメタデータを持つことを検証。

	条件：members を items に、non-negative total をメタデータに設定してMemberListResponse を作成したとき、各フィールドが正しく保持されること。
	"""
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
	"""
	MemberListMeta が negative total を拒否することを検証。

	条件：total=-1 を指定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		MemberListMeta(total=-1)


@pytest.mark.parametrize("user_id", ["not-a-uuid", uuid1()])
def test_add_member_request_requires_uuid4(user_id: object) -> None:
	"""
	AddMemberRequest が user_id として UUID4 を要求し、UUID1 や invalid UUID を拒否することを検証。

	条件：UUID4 でない user_id（UUID1 形式、文字列）を指定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		AddMemberRequest(user_id=user_id)


def test_candidate_search_query_accepts_boundary_lengths() -> None:
	"""
	CandidateSearchQuery が検索クエリの境界値（1～50文字）を受け入れることを検証。

	条件：q が1文字および50文字のいずれのときも、フィールドが正しく保持されること。
	"""
	assert CandidateSearchQuery(q="a").q == "a"
	assert CandidateSearchQuery(q="a" * 50).q == "a" * 50


@pytest.mark.parametrize("query", ["", "a" * 51])
def test_candidate_search_query_rejects_out_of_range_length(query: str) -> None:
	"""
	CandidateSearchQuery が範囲外の長さ（空、51文字超）を拒否することを検証。

	条件：q が空または51文字超のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		CandidateSearchQuery(q=query)


def test_candidate_list_response_contains_only_non_email_candidate_fields() -> None:
	"""
	CandidateListResponse が candidate 情報（メール以外のフィールド）のみを含むことを検証。

	条件：CandidateSummary（user_id、username、display_name）を items に含めてCandidateListResponse を作成したとき、model_dump() に email フィールドが含まれないこと。
	"""
	candidate = CandidateSummary(user_id=uuid4(), username="hanako", display_name="鈴木 花子")
	response = CandidateListResponse(items=[candidate])

	assert response.items[0] == candidate
	assert "email" not in response.model_dump()

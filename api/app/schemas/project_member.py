from datetime import datetime
from typing import Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field

MemberRole = Literal["member", "admin"]


class MemberListQueryParams(BaseModel):
	project_id: UUID4


class MemberDeletePathParams(MemberListQueryParams):
	user_id: UUID4


class AddMemberRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	user_id: UUID4


class MemberSummary(BaseModel):
	user_id: UUID4
	username: str
	display_name: str | None
	role: MemberRole
	is_owner: bool
	is_active: bool
	joined_at: datetime


class MemberResponse(MemberSummary):
	pass


class MemberListMeta(BaseModel):
	total: int = Field(ge=0)


class MemberListResponse(BaseModel):
	items: list[MemberSummary]
	meta: MemberListMeta


class CandidateSearchQuery(BaseModel):
	model_config = ConfigDict(extra="forbid")

	q: str = Field(min_length=1, max_length=50)


class CandidateSummary(BaseModel):
	user_id: UUID4
	username: str
	display_name: str | None


class CandidateListResponse(BaseModel):
	items: list[CandidateSummary]

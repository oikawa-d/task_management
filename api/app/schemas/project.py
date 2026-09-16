from datetime import datetime
from typing import Self, cast
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.config import BackendSettings

_PAGINATION_DEFAULT_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_default_per_page"].default)
_PAGINATION_MAX_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_max_per_page"].default)


class ProjectListQuery(BaseModel):
	page: int = Field(default=1, ge=1)
	per_page: int = Field(default=_PAGINATION_DEFAULT_PER_PAGE, ge=1, le=_PAGINATION_MAX_PER_PAGE)
	include_inactive: bool = False


class ProjectCreateRequest(BaseModel):
	name: str = Field(min_length=1, max_length=100)
	description: str | None = None
	start_at: datetime | None = None
	end_at: datetime | None = None

	@model_validator(mode="after")
	def validate_period(self) -> Self:
		if self.start_at is not None and self.end_at is not None and self.end_at < self.start_at:
			raise ValueError("end_at must be greater than or equal to start_at")
		return self


class ProjectUpdateRequest(BaseModel):
	name: str | None = Field(default=None, min_length=1, max_length=100)
	description: str | None = None
	start_at: datetime | None = None
	end_at: datetime | None = None
	is_active: bool | None = None

	@model_validator(mode="before")
	@classmethod
	def validate_non_nullable_fields(cls, value: object) -> object:
		if isinstance(value, dict):
			for field_name in ("name", "is_active"):
				if field_name in value and value[field_name] is None:
					raise ValueError(f"{field_name} must not be null")
		return value

	@model_validator(mode="after")
	def validate_at_least_one_field(self) -> Self:
		if not self.model_fields_set:
			raise ValueError("at least one field must be specified")
		return self


class ProjectPathParams(BaseModel):
	project_id: UUID


class ProjectOwner(BaseModel):
	id: UUID
	username: str
	display_name: str


class ProjectTaskCounts(BaseModel):
	todo: int = Field(ge=0)
	in_progress: int = Field(ge=0)
	done: int = Field(ge=0)


class ProjectMember(BaseModel):
	user_id: UUID
	username: str
	display_name: str
	is_owner: bool
	joined_at: datetime


class ProjectSummary(BaseModel):
	id: UUID
	name: str
	description: str | None
	owner: ProjectOwner
	member_count: int = Field(ge=0)
	task_counts: ProjectTaskCounts
	is_owner: bool
	is_active: bool
	start_at: datetime | None
	end_at: datetime | None
	created_at: datetime


class ProjectSummaryResponse(ProjectSummary):
	updated_at: datetime | None = None


class ProjectDetail(ProjectSummary):
	updated_at: datetime
	members: list[ProjectMember]


class ProjectDetailResponse(ProjectDetail):
	pass


class ProjectListMeta(BaseModel):
	page: int = Field(ge=1)
	per_page: int = Field(ge=1, le=_PAGINATION_MAX_PER_PAGE)
	total: int = Field(ge=0)
	total_pages: int = Field(ge=0)


class ProjectListResponse(BaseModel):
	items: list[ProjectSummaryResponse]
	meta: ProjectListMeta

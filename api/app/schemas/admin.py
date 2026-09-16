from datetime import datetime
from typing import Literal, cast

from pydantic import UUID4, ConfigDict, Field, field_validator, model_validator

from app.core.config import BackendSettings, get_backend_settings
from app.schemas.base import StrictSchema
from app.schemas.user import LoginMethod

AdminRole = Literal["member", "admin"]
_DEFAULT_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_default_per_page"].default)
_MAX_PER_PAGE = cast(int, BackendSettings.model_fields["pagination_max_per_page"].default)


def _validate_search_query(value: str | None) -> str | None:
	if value is not None and len(value) > get_backend_settings().admin_search_query_max_length:
		raise ValueError("search query exceeds the configured maximum length")
	return value


class AdminPaginationQuery(StrictSchema):
	page: int = Field(default=1, ge=1)
	per_page: int = Field(default=_DEFAULT_PER_PAGE, ge=1, le=_MAX_PER_PAGE)


class AdminUserListQuery(AdminPaginationQuery):
	q: str | None = None
	role: AdminRole | None = None
	is_active: bool | None = None

	@field_validator("q")
	@classmethod
	def validate_query_length(cls, value: str | None) -> str | None:
		return _validate_search_query(value)


class AdminUserRoleUpdateRequest(StrictSchema):
	role: AdminRole


class AdminUserStatusUpdateRequest(StrictSchema):
	is_active: bool


class AdminUserItem(StrictSchema):
	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	username: str
	email: str
	display_name: str
	role: AdminRole
	is_active: bool
	email_verified_at: datetime | None
	created_at: datetime


class AdminUserListMeta(StrictSchema):
	page: int = Field(ge=1)
	per_page: int = Field(ge=1, le=_MAX_PER_PAGE)
	total: int = Field(ge=0)
	total_pages: int = Field(ge=0)


class AdminUserListResponse(StrictSchema):
	items: list[AdminUserItem]
	meta: AdminUserListMeta


class AdminUserDetailResponse(AdminUserItem):
	updated_at: datetime


class AdminProjectListQuery(AdminPaginationQuery):
	q: str | None = None

	@field_validator("q")
	@classmethod
	def validate_query_length(cls, value: str | None) -> str | None:
		return _validate_search_query(value)


class AdminProjectListMeta(AdminUserListMeta):
	pass


class AdminProjectOwner(StrictSchema):
	id: UUID4
	username: str
	display_name: str


class AdminProjectTaskCounts(StrictSchema):
	todo: int = Field(ge=0)
	in_progress: int = Field(ge=0)
	done: int = Field(ge=0)


class AdminProjectSummary(StrictSchema):
	id: UUID4
	name: str
	description: str | None
	owner: AdminProjectOwner
	member_count: int = Field(ge=0)
	task_counts: AdminProjectTaskCounts
	is_active: bool
	start_at: datetime | None
	end_at: datetime | None
	created_at: datetime


class AdminProjectListResponse(StrictSchema):
	items: list[AdminProjectSummary]
	meta: AdminProjectListMeta


class AdminLoginHistoryQuery(AdminPaginationQuery):
	model_config = ConfigDict(extra="forbid", populate_by_name=True)

	user_id: UUID4 | None = None
	q: str | None = None
	login_method: LoginMethod | None = None
	success: bool | None = None
	created_from: datetime | None = Field(default=None, alias="from")
	created_to: datetime | None = Field(default=None, alias="to")

	@field_validator("q")
	@classmethod
	def validate_query_length(cls, value: str | None) -> str | None:
		return _validate_search_query(value)

	@model_validator(mode="after")
	def validate_period(self) -> "AdminLoginHistoryQuery":
		if self.created_from is not None and self.created_to is not None and self.created_from >= self.created_to:
			raise ValueError("from must be earlier than to")
		return self


class AdminLoginHistoryUser(StrictSchema):
	id: UUID4
	username: str
	display_name: str


class AdminLoginHistoryItem(StrictSchema):
	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	user: AdminLoginHistoryUser | None
	login_identifier: str
	login_method: LoginMethod
	ip_address: str | None
	user_agent: str | None
	success: bool
	failure_reason: str | None
	created_at: datetime


class AdminLoginHistoryListResponse(StrictSchema):
	items: list[AdminLoginHistoryItem]
	meta: AdminUserListMeta

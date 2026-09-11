from datetime import date, datetime
from typing import Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import get_backend_settings

TaskStatus = Literal["todo", "in_progress", "done"]
TaskSort = Literal["created_at", "due_at"]
TaskOrder = Literal["asc", "desc"]
CalendarScope = Literal["me", "project"]


def _default_per_page() -> int:
	return get_backend_settings().pagination_default_per_page


class TaskAssignee(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	username: str
	display_name: str


class TaskCreator(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	username: str
	display_name: str | None = None


class TaskCreateRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	title: str = Field(min_length=1, max_length=150)
	description: str | None = None
	status: TaskStatus = "todo"
	assignee_id: UUID4 | None = None
	due_at: datetime | None = None


class TaskCreateFlatRequest(TaskCreateRequest):
	project_id: UUID4 | None = None

	@model_validator(mode="after")
	def reject_assignee_without_project(self) -> "TaskCreateFlatRequest":
		if self.project_id is None and self.assignee_id is not None:
			raise ValueError("assignee_id cannot be set for an unassigned task")
		return self


class TaskUpdateRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	version: int
	title: str | None = Field(default=None, min_length=1, max_length=150)
	description: str | None = Field(default=None, max_length=2000)
	status: TaskStatus | None = None
	assignee_id: UUID4 | None = None
	position: int | None = Field(default=None, ge=0)
	due_at: datetime | None = None
	is_active: bool | None = None

	@model_validator(mode="after")
	def reject_null_for_non_nullable_fields(self) -> "TaskUpdateRequest":
		for field_name in ("title", "status", "position", "is_active"):
			if field_name in self.model_fields_set and getattr(self, field_name) is None:
				raise ValueError(f"{field_name} cannot be null")
		return self


class TaskSummary(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	title: str
	description: str | None
	assignee: TaskAssignee | None
	due_at: datetime | None
	position: int
	version: int
	is_active: bool
	comment_count: int
	created_at: datetime
	updated_at: datetime


class TaskResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID4
	project_id: UUID4 | None
	project_is_active: bool | None
	title: str
	description: str | None
	status: TaskStatus
	assignee: TaskAssignee | None
	created_by: TaskCreator
	position: int
	version: int
	is_active: bool
	due_at: datetime | None
	created_at: datetime
	updated_at: datetime


class TaskDetailResponse(TaskResponse):
	comment_count: int


class TaskListItem(TaskDetailResponse):
	pass


class BoardColumns(BaseModel):
	todo: list[TaskSummary] = Field(default_factory=list)
	in_progress: list[TaskSummary] = Field(default_factory=list)
	done: list[TaskSummary] = Field(default_factory=list)


class BoardResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	project_id: UUID4
	project_is_active: bool
	columns: BoardColumns


class TaskListQuery(BaseModel):
	page: int = Field(default=1, ge=1)
	per_page: int = Field(default_factory=_default_per_page, ge=1)
	project_id: UUID4 | Literal["unassigned"] | None = None
	status: TaskStatus | None = None
	include_inactive: bool = False
	sort: TaskSort = "created_at"
	order: TaskOrder = "desc"

	@field_validator("project_id", mode="before")
	@classmethod
	def normalize_unassigned_filter(cls, value: object) -> object:
		if value == "null":
			return "unassigned"
		if value == "unassigned":
			raise ValueError('project_id must be a UUID or "null"')
		return value

	@field_validator("per_page")
	@classmethod
	def validate_per_page_limit(cls, value: int) -> int:
		if value > get_backend_settings().pagination_max_per_page:
			raise ValueError("per_page exceeds the configured maximum")
		return value


class TaskListMeta(BaseModel):
	page: int = Field(ge=1)
	per_page: int = Field(ge=1)
	total: int = Field(ge=0)
	total_pages: int = Field(ge=0)


class TaskListResponse(BaseModel):
	items: list[TaskListItem]
	meta: TaskListMeta


class CalendarTaskQuery(BaseModel):
	from_date: date = Field(alias="from")
	to_date: date = Field(alias="to")
	scope: CalendarScope
	project_id: UUID4 | None = None

	@model_validator(mode="after")
	def validate_range_and_scope(self) -> "CalendarTaskQuery":
		if self.to_date < self.from_date or (self.to_date - self.from_date).days > 62:
			raise ValueError("calendar range must be within 62 days")
		if self.scope == "project" and self.project_id is None:
			raise ValueError("project_id is required for project scope")
		if self.scope == "me" and self.project_id is not None:
			raise ValueError("project_id is not allowed for me scope")
		return self

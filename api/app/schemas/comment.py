from datetime import datetime
from uuid import UUID

from pydantic import UUID4, ConfigDict, Field, field_validator

from app.core.config import get_backend_settings
from app.schemas.base import StrictSchema


def _validate_body_length(value: str) -> str:
	if len(value) > get_backend_settings().task_comment_body_max_length:
		raise ValueError("comment body exceeds the configured maximum length")
	return value


class CommentAuthor(StrictSchema):
	id: UUID4
	username: str
	display_name: str


class CommentCreateRequest(StrictSchema):
	model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

	body: str = Field(min_length=1)

	@field_validator("body")
	@classmethod
	def validate_body(cls, value: str) -> str:
		return _validate_body_length(value)


class CommentUpdateRequest(CommentCreateRequest):
	pass


class CommentResponse(StrictSchema):
	id: UUID4
	task_id: UUID4
	body: str
	author: CommentAuthor
	created_at: datetime
	updated_at: datetime


class CommentListResponse(StrictSchema):
	task_id: UUID
	items: list[CommentResponse]
	count: int = Field(ge=0)

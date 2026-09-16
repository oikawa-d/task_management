import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

KANA_PATTERN = r"^[ぁ-んァ-ヶー0-9]+$"
LoginMethod = Literal["session", "jwt", "oauth_google"]


class UserProfileResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	username: str
	email: str
	last_name: str | None
	first_name: str | None
	last_name_kana: str | None
	first_name_kana: str | None
	birth_date: date | None
	profile_completed: bool
	role: Literal["member", "admin"]
	has_password: bool
	oauth_providers: list[str]


class UserProfileUpdateRequest(BaseModel):
	last_name: str | None = Field(default=None, min_length=1, max_length=30)
	first_name: str | None = Field(default=None, min_length=1, max_length=30)
	last_name_kana: str | None = Field(default=None, min_length=1, max_length=30, pattern=KANA_PATTERN)
	first_name_kana: str | None = Field(default=None, min_length=1, max_length=30, pattern=KANA_PATTERN)
	birth_date: date | None = None

	@field_validator("birth_date")
	@classmethod
	def validate_birth_date(cls, value: date | None) -> date | None:
		if value is not None and value > date.today():
			raise ValueError("birth date must not be in the future")
		return value


class PasswordChangeRequest(BaseModel):
	current_password: str | None = None
	new_password: str = Field(min_length=8)
	password_confirm: str

	@field_validator("new_password")
	@classmethod
	def validate_password_categories(cls, value: str) -> str:
		categories = (
			bool(re.search(r"[A-Z]", value)),
			bool(re.search(r"[a-z]", value)),
			bool(re.search(r"[0-9]", value)),
			bool(re.search(r"[^A-Za-z0-9]", value)),
		)
		if sum(categories) < 2:
			raise ValueError("password must contain at least two character categories")
		return value

	@model_validator(mode="after")
	def validate_confirmation(self) -> "PasswordChangeRequest":
		if self.new_password != self.password_confirm:
			raise ValueError("password confirmation does not match")
		return self


class LoginHistoryItem(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: UUID
	login_method: LoginMethod
	ip_address: str | None
	user_agent: str | None
	success: bool
	failure_reason: str | None
	created_at: datetime


class LoginHistoryMeta(BaseModel):
	limit: int = Field(ge=1)
	count: int = Field(ge=0)


class LoginHistoryListResponse(BaseModel):
	items: list[LoginHistoryItem]
	meta: LoginHistoryMeta

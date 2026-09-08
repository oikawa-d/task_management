import re
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

USERNAME_PATTERN = r"^[A-Za-z0-9_-]+$"
KANA_PATTERN = r"^[ぁ-んァ-ヶー0-9]+$"
EMAIL_PATTERN = r"^[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"


class _AuthSchema(BaseModel):
	model_config = ConfigDict(extra="forbid")


def _validate_email(value: str) -> str:
	if re.fullmatch(EMAIL_PATTERN, value) is None:
		raise ValueError("invalid email format")
	return value


def _validate_password_categories(value: str) -> str:
	categories = (
		bool(re.search(r"[A-Z]", value)),
		bool(re.search(r"[a-z]", value)),
		bool(re.search(r"[0-9]", value)),
		bool(re.search(r"[^A-Za-z0-9]", value)),
	)
	if sum(categories) < 2:
		raise ValueError("password must contain at least two character categories")
	return value


class RegisterRequest(_AuthSchema):
	username: str = Field(min_length=3, max_length=50, pattern=USERNAME_PATTERN)
	email: str = Field(max_length=50)
	password: str = Field(min_length=8)
	password_confirm: str
	last_name: str = Field(min_length=1, max_length=30)
	first_name: str = Field(min_length=1, max_length=30)
	last_name_kana: str = Field(min_length=1, max_length=30, pattern=KANA_PATTERN)
	first_name_kana: str = Field(min_length=1, max_length=30, pattern=KANA_PATTERN)
	birth_date: date

	@field_validator("email")
	@classmethod
	def validate_email(cls, value: str) -> str:
		return _validate_email(value)

	@field_validator("password")
	@classmethod
	def validate_password_categories(cls, value: str) -> str:
		return _validate_password_categories(value)

	@model_validator(mode="after")
	def validate_confirmation_and_birth_date(self) -> "RegisterRequest":
		if self.password != self.password_confirm:
			raise ValueError("password confirmation does not match")
		if self.birth_date > date.today():
			raise ValueError("birth date must not be in the future")
		return self


class RegisterResponse(_AuthSchema):
	id: UUID
	email: str
	message: str


class LoginRequest(_AuthSchema):
	identifier: str = Field(min_length=1, max_length=50)
	password: str = Field(min_length=1)


class LoginResponse(_AuthSchema):
	access_token: str
	token_type: Literal["bearer"]
	expires_in: int


class RefreshResponse(_AuthSchema):
	access_token: str
	token_type: Literal["bearer"]
	expires_in: int


class VerifyEmailRequest(_AuthSchema):
	token: str = Field(min_length=1)


class ResendVerifyEmailRequest(_AuthSchema):
	email: str = Field(max_length=50)

	@field_validator("email")
	@classmethod
	def validate_email(cls, value: str) -> str:
		return _validate_email(value)


class ResendVerifyEmailResponse(_AuthSchema):
	message: str


class PasswordForgotRequest(_AuthSchema):
	email: str = Field(max_length=50)

	@field_validator("email")
	@classmethod
	def validate_email(cls, value: str) -> str:
		return _validate_email(value)


class PasswordForgotResponse(_AuthSchema):
	message: str


class PasswordResetRequest(_AuthSchema):
	token: str = Field(min_length=1)
	new_password: str = Field(min_length=8)
	password_confirm: str

	@field_validator("new_password")
	@classmethod
	def validate_password_categories(cls, value: str) -> str:
		return _validate_password_categories(value)

	@model_validator(mode="after")
	def validate_confirmation(self) -> "PasswordResetRequest":
		if self.new_password != self.password_confirm:
			raise ValueError("password confirmation does not match")
		return self


class MeResponse(_AuthSchema):
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
	auth_mode: Literal["session", "jwt"]


class AuthConfigResponse(_AuthSchema):
	auth_mode: Literal["session", "jwt"]
	google_login_enabled: bool
	csrf_cookie_name: str

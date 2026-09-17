from typing import Literal

from pydantic import Field, field_validator

from app.core.input_validation import validate_auth_token_max_length
from app.schemas.base import StrictSchema


class OAuthStartResult(StrictSchema):
	authorize_url: str = Field(min_length=1)
	state: str = Field(min_length=1)


class OAuthCallbackQuery(StrictSchema):
	code: str | None = None
	state: str | None = None
	error: str | None = None

	@field_validator("code", "state")
	@classmethod
	def validate_query_token_length(cls, value: str | None) -> str | None:
		return None if value is None else validate_auth_token_max_length(value)


class OAuthCallbackResult(StrictSchema):
	auth_mode: Literal["session", "jwt"]
	redirect_to: str = Field(min_length=1)
	handoff_code: str | None = Field(default=None, min_length=1)


class OAuthExchangeRequest(StrictSchema):
	code: str = Field(min_length=1)

	@field_validator("code")
	@classmethod
	def validate_code_length(cls, value: str) -> str:
		return validate_auth_token_max_length(value)


class OAuthExchangeResponse(StrictSchema):
	access_token: str = Field(min_length=1)
	token_type: Literal["bearer"]
	expires_in: int = Field(ge=1)
	redirect_to: str = Field(min_length=1)

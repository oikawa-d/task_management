from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _OAuthSchema(BaseModel):
	model_config = ConfigDict(extra="forbid")


class OAuthStartResult(_OAuthSchema):
	authorize_url: str = Field(min_length=1)
	state: str = Field(min_length=1)


class OAuthCallbackResult(_OAuthSchema):
	auth_mode: Literal["session", "jwt"]
	redirect_to: str = Field(min_length=1)
	handoff_code: str | None = Field(default=None, min_length=1)


class OAuthExchangeRequest(_OAuthSchema):
	code: str = Field(min_length=1)


class OAuthExchangeResponse(_OAuthSchema):
	access_token: str = Field(min_length=1)
	token_type: Literal["bearer"]
	expires_in: int = Field(ge=1)
	redirect_to: str = Field(min_length=1)

from typing import Literal

from pydantic import Field

from app.schemas.base import StrictSchema


class OAuthStartResult(StrictSchema):
	authorize_url: str = Field(min_length=1)
	state: str = Field(min_length=1)


class OAuthCallbackResult(StrictSchema):
	auth_mode: Literal["session", "jwt"]
	redirect_to: str = Field(min_length=1)
	handoff_code: str | None = Field(default=None, min_length=1)


class OAuthExchangeRequest(StrictSchema):
	code: str = Field(min_length=1)


class OAuthExchangeResponse(StrictSchema):
	access_token: str = Field(min_length=1)
	token_type: Literal["bearer"]
	expires_in: int = Field(ge=1)
	redirect_to: str = Field(min_length=1)

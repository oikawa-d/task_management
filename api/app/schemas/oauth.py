"""Google OAuthログイン関連エンドポイント（`oauth_router`）の入出力DTOを定義するモジュール。"""

from typing import Literal

from pydantic import Field, field_validator

from app.core.input_validation import validate_auth_token_max_length
from app.schemas.base import StrictSchema


class OAuthStartResult(StrictSchema):
	"""`GET /auth/oauth/google/start` のレスポンスDTO。Google認可画面へのリダイレクト先とCSRF対策用stateを返す。"""

	authorize_url: str = Field(min_length=1)
	state: str = Field(min_length=1)


class OAuthCallbackQuery(StrictSchema):
	"""`GET /auth/oauth/google/callback` のクエリパラメータDTO。Google側から返却される認可コード等を受け取る。"""

	code: str | None = None
	state: str | None = None
	error: str | None = None

	@field_validator("code", "state")
	@classmethod
	def validate_query_token_length(cls, value: str | None) -> str | None:
		"""`code`/`state` が認証トークンの許容最大長を超えていないかを検証する。

		Args:
			value: 検証対象の値。未指定（`None`）の場合は検証をスキップする。

		Returns:
			検証を通過した値。

		Raises:
			ValueError: 許容最大長を超えている場合。
		"""
		return None if value is None else validate_auth_token_max_length(value)


class OAuthCallbackResult(StrictSchema):
	"""OAuthコールバック処理結果を表すDTO。認証方式に応じたリダイレクト先と、JWTモード時の引換コードを保持する。"""

	auth_mode: Literal["session", "jwt"]
	redirect_to: str = Field(min_length=1)
	handoff_code: str | None = Field(default=None, min_length=1)


class OAuthExchangeRequest(StrictSchema):
	"""`POST /auth/oauth/exchange` のリクエストDTO。コールバックで発行された引換コードをアクセストークンに交換する。"""

	code: str = Field(min_length=1)

	@field_validator("code")
	@classmethod
	def validate_code_length(cls, value: str) -> str:
		"""引換コードが認証トークンの許容最大長を超えていないかを検証する。

		Args:
			value: 検証対象の引換コード。

		Returns:
			検証を通過した値。

		Raises:
			ValueError: 許容最大長を超えている場合。
		"""
		return validate_auth_token_max_length(value)


class OAuthExchangeResponse(StrictSchema):
	"""`POST /auth/oauth/exchange` のレスポンスDTO。JWTモードでのアクセストークン発行結果を返す。"""

	access_token: str = Field(min_length=1)
	token_type: Literal["bearer"]
	expires_in: int = Field(ge=1)
	redirect_to: str = Field(min_length=1)

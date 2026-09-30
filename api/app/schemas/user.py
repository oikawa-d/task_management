"""ユーザー自身のプロフィール・パスワード・ログイン履歴系エンドポイント（`users_router`）の入出力DTOを定義するモジュール。"""

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import PASSWORD_MIN_LENGTH
from app.core.input_validation import validate_password_max_length

KANA_PATTERN = r"^[ぁ-んァ-ヶー0-9]+$"
LoginMethod = Literal["session", "jwt", "oauth_google"]


class UserProfileResponse(BaseModel):
	"""`GET /api/users/me` のレスポンスDTO。ORMの`User`から`from_attributes`で変換する。"""

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
	"""`PATCH /api/users/me` のリクエストDTO。"""

	last_name: str | None = Field(default=None, min_length=1, max_length=30)
	first_name: str | None = Field(default=None, min_length=1, max_length=30)
	last_name_kana: str | None = Field(default=None, min_length=1, max_length=30, pattern=KANA_PATTERN)
	first_name_kana: str | None = Field(default=None, min_length=1, max_length=30, pattern=KANA_PATTERN)
	birth_date: date | None = None

	@field_validator("birth_date")
	@classmethod
	def validate_birth_date(cls, value: date | None) -> date | None:
		"""生年月日が未来日でないことを検証する。

		Args:
			value: 検証対象の生年月日。未指定（`None`）の場合は検証をスキップする。

		Returns:
			検証を通過した値。

		Raises:
			ValueError: 生年月日が本日より未来の場合。
		"""
		if value is not None and value > date.today():
			raise ValueError("birth date must not be in the future")
		return value


class PasswordChangeRequest(BaseModel):
	"""`PUT /api/users/me/password` のリクエストDTO。パスワード有無に応じ現在パスワードの要否をservice層で判定する。"""

	current_password: str | None = None
	new_password: str = Field(min_length=PASSWORD_MIN_LENGTH)
	password_confirm: str

	@field_validator("current_password", "password_confirm")
	@classmethod
	def validate_password_field_length(cls, value: str | None) -> str | None:
		"""現在パスワード・確認用パスワードが許容最大長を超えていないかを検証する。

		Args:
			value: 検証対象の値。未指定（`None`）の場合は検証をスキップする。

		Returns:
			検証を通過した値。

		Raises:
			ValueError: 許容最大長を超えている場合。
		"""
		return None if value is None else validate_password_max_length(value)

	@field_validator("new_password")
	@classmethod
	def validate_password_categories(cls, value: str) -> str:
		"""新パスワードが大文字・小文字・数字・記号のうち2種類以上を含み、かつ許容最大長以内であることを検証する。

		Args:
			value: 検証対象の新パスワード。

		Returns:
			検証を通過した値。

		Raises:
			ValueError: 文字種が2種類未満の場合、または許容最大長を超えている場合。
		"""
		categories = (
			bool(re.search(r"[A-Z]", value)),
			bool(re.search(r"[a-z]", value)),
			bool(re.search(r"[0-9]", value)),
			bool(re.search(r"[^A-Za-z0-9]", value)),
		)
		if sum(categories) < 2:
			raise ValueError("password must contain at least two character categories")
		return validate_password_max_length(value)

	@model_validator(mode="after")
	def validate_confirmation(self) -> "PasswordChangeRequest":
		"""新パスワードと確認用パスワードが一致することを検証する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: 両者が一致しない場合。
		"""
		if self.new_password != self.password_confirm:
			raise ValueError("password confirmation does not match")
		return self


class LoginHistoryItem(BaseModel):
	"""ログイン履歴1件分のレスポンスDTO。ORMの`LoginHistory`から`from_attributes`で変換する。"""

	model_config = ConfigDict(from_attributes=True)

	id: UUID
	login_method: LoginMethod
	ip_address: str | None
	user_agent: str | None
	success: bool
	failure_reason: str | None
	created_at: datetime


class LoginHistoryMeta(BaseModel):
	"""ログイン履歴一覧のメタ情報DTO。取得上限件数と実件数を保持する。"""

	limit: int = Field(ge=1)
	count: int = Field(ge=0)


class LoginHistoryListResponse(BaseModel):
	"""`GET /api/users/me/login-history` のレスポンスDTO。"""

	items: list[LoginHistoryItem]
	meta: LoginHistoryMeta

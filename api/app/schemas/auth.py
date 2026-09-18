"""認証系エンドポイント（`auth_router`：登録・ログイン・トークン更新・メール確認・パスワード再設定等）の入出力DTOを定義するモジュール。"""

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.core.constants import EMAIL_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.core.input_validation import validate_auth_token_max_length, validate_password_max_length
from app.schemas.base import StrictSchema

USERNAME_PATTERN = r"^[A-Za-z0-9_-]+$"
KANA_PATTERN = r"^[ぁ-んァ-ヶー0-9]+$"
EMAIL_PATTERN = r"^[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"


def _validate_email(value: str) -> str:
	"""メールアドレスがアプリ規定の形式（`EMAIL_PATTERN`）に合致することを検証する。

	Args:
		value: 検証対象のメールアドレス。

	Returns:
		検証を通過した値。

	Raises:
		ValueError: 形式に合致しない場合。
	"""
	if re.fullmatch(EMAIL_PATTERN, value) is None:
		raise ValueError("invalid email format")
	return value


def _validate_password_categories(value: str) -> str:
	"""パスワードが大文字・小文字・数字・記号のうち2種類以上を含むことを検証する。

	Args:
		value: 検証対象のパスワード。

	Returns:
		検証を通過した値。

	Raises:
		ValueError: 含まれる文字種が2種類未満の場合。
	"""
	categories = (
		bool(re.search(r"[A-Z]", value)),
		bool(re.search(r"[a-z]", value)),
		bool(re.search(r"[0-9]", value)),
		bool(re.search(r"[^A-Za-z0-9]", value)),
	)
	if sum(categories) < 2:
		raise ValueError("password must contain at least two character categories")
	return value


class RegisterRequest(StrictSchema):
	"""`POST /auth/register` のリクエストDTO。"""

	username: str = Field(min_length=3, max_length=50, pattern=USERNAME_PATTERN)
	email: str = Field(max_length=EMAIL_MAX_LENGTH)
	password: str = Field(min_length=PASSWORD_MIN_LENGTH)
	password_confirm: str
	last_name: str = Field(min_length=1, max_length=30)
	first_name: str = Field(min_length=1, max_length=30)
	last_name_kana: str = Field(min_length=1, max_length=30, pattern=KANA_PATTERN)
	first_name_kana: str = Field(min_length=1, max_length=30, pattern=KANA_PATTERN)
	birth_date: date

	@field_validator("email")
	@classmethod
	def validate_email(cls, value: str) -> str:
		"""メールアドレスの形式を検証するフィールドバリデータ。`_validate_email`に委譲する。"""
		return _validate_email(value)

	@field_validator("password")
	@classmethod
	def validate_password_categories(cls, value: str) -> str:
		"""パスワードの文字種構成と許容最大長を検証するフィールドバリデータ。"""
		return validate_password_max_length(_validate_password_categories(value))

	@field_validator("password_confirm")
	@classmethod
	def validate_password_confirmation_length(cls, value: str) -> str:
		"""確認用パスワードが許容最大長を超えていないかを検証するフィールドバリデータ。"""
		return validate_password_max_length(value)

	@model_validator(mode="after")
	def validate_confirmation_and_birth_date(self) -> "RegisterRequest":
		"""パスワード確認の一致と、生年月日が未来日でないことを検証する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: パスワード確認が一致しない場合、または生年月日が未来日の場合。
		"""
		if self.password != self.password_confirm:
			raise ValueError("password confirmation does not match")
		if self.birth_date > date.today():
			raise ValueError("birth date must not be in the future")
		return self


class RegisterResponse(StrictSchema):
	"""`POST /auth/register` のレスポンスDTO。"""

	id: UUID
	email: str
	message: str


class LoginRequest(StrictSchema):
	"""`POST /auth/login` のリクエストDTO。ユーザー名またはメールアドレスでのログインを受け付ける。"""

	identifier: str = Field(min_length=1, max_length=EMAIL_MAX_LENGTH)
	password: str = Field(min_length=1)

	@field_validator("password")
	@classmethod
	def validate_password_length(cls, value: str) -> str:
		"""パスワードが許容最大長を超えていないかを検証するフィールドバリデータ。"""
		return validate_password_max_length(value)


class LoginResponse(StrictSchema):
	"""`POST /auth/login` のレスポンスDTO（JWTモード時）。"""

	access_token: str
	token_type: Literal["bearer"]
	expires_in: int


class RefreshResponse(StrictSchema):
	"""`POST /auth/refresh` のレスポンスDTO。新しいアクセストークンを返す。"""

	access_token: str
	token_type: Literal["bearer"]
	expires_in: int


class VerifyEmailRequest(StrictSchema):
	"""`POST /auth/verify-email` のリクエストDTO。"""

	token: str = Field(min_length=1)

	@field_validator("token")
	@classmethod
	def validate_token_length(cls, value: str) -> str:
		"""確認トークンが許容最大長を超えていないかを検証するフィールドバリデータ。"""
		return validate_auth_token_max_length(value)


class ResendVerifyEmailRequest(StrictSchema):
	"""`POST /auth/verify-email/resend` のリクエストDTO。"""

	email: str = Field(max_length=EMAIL_MAX_LENGTH)

	@field_validator("email")
	@classmethod
	def validate_email(cls, value: str) -> str:
		"""メールアドレスの形式を検証するフィールドバリデータ。`_validate_email`に委譲する。"""
		return _validate_email(value)


class ResendVerifyEmailResponse(StrictSchema):
	"""`POST /auth/verify-email/resend` のレスポンスDTO。"""

	message: str


class PasswordForgotRequest(StrictSchema):
	"""`POST /auth/password/forgot` のリクエストDTO。"""

	email: str = Field(max_length=EMAIL_MAX_LENGTH)

	@field_validator("email")
	@classmethod
	def validate_email(cls, value: str) -> str:
		"""メールアドレスの形式を検証するフィールドバリデータ。`_validate_email`に委譲する。"""
		return _validate_email(value)


class PasswordForgotResponse(StrictSchema):
	"""`POST /auth/password/forgot` のレスポンスDTO。"""

	message: str


class PasswordResetRequest(StrictSchema):
	"""`POST /auth/password/reset` のリクエストDTO。"""

	token: str = Field(min_length=1)
	new_password: str = Field(min_length=PASSWORD_MIN_LENGTH)
	password_confirm: str

	@field_validator("token")
	@classmethod
	def validate_token_length(cls, value: str) -> str:
		"""リセットトークンが許容最大長を超えていないかを検証するフィールドバリデータ。"""
		return validate_auth_token_max_length(value)

	@field_validator("new_password")
	@classmethod
	def validate_password_categories(cls, value: str) -> str:
		"""新パスワードの文字種構成と許容最大長を検証するフィールドバリデータ。"""
		return validate_password_max_length(_validate_password_categories(value))

	@field_validator("password_confirm")
	@classmethod
	def validate_password_confirmation_length(cls, value: str) -> str:
		"""確認用パスワードが許容最大長を超えていないかを検証するフィールドバリデータ。"""
		return validate_password_max_length(value)

	@model_validator(mode="after")
	def validate_confirmation(self) -> "PasswordResetRequest":
		"""新パスワードと確認用パスワードが一致することを検証する。

		Returns:
			検証を通過した自インスタンス。

		Raises:
			ValueError: 両者が一致しない場合。
		"""
		if self.new_password != self.password_confirm:
			raise ValueError("password confirmation does not match")
		return self


class MeResponse(StrictSchema):
	"""`GET /auth/me` のレスポンスDTO。ログイン中ユーザーのプロフィールと認証状態をまとめて返す。"""

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


class AuthConfigResponse(StrictSchema):
	"""`GET /auth/config` のレスポンスDTO。フロントエンドが参照する認証方式・機能有効化状態を返す。"""

	auth_mode: Literal["session", "jwt"]
	google_login_enabled: bool
	csrf_cookie_name: str


class CurrentUser(StrictSchema):
	"""認証済みリクエストのコンテキストとして各エンドポイント内部で利用するログインユーザー情報のDTO。"""

	id: UUID
	username: str
	role: Literal["member", "admin"]
	is_active: bool
	email_verified_at: datetime | None

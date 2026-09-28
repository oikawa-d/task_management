"""
認証関連スキーマのバリデーション・フィールド制限・トークン制限を検証するテスト。
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from app.core.config import get_backend_settings
from app.schemas.auth import (
	AuthConfigResponse,
	CurrentUser,
	LoginRequest,
	LoginResponse,
	MeResponse,
	PasswordForgotRequest,
	PasswordForgotResponse,
	PasswordResetRequest,
	RefreshResponse,
	RegisterRequest,
	RegisterResponse,
	ResendVerifyEmailRequest,
	ResendVerifyEmailResponse,
	VerifyEmailRequest,
)
from app.schemas.base import StrictSchema
from app.schemas.oauth import OAuthCallbackQuery, OAuthExchangeRequest
from pydantic import ValidationError


def _register_payload(**overrides: object) -> dict[str, object]:
	"""
	RegisterRequest テストのためのベースペイロードを生成。

	Args:
		**overrides: ベースペイロードの指定フィールドを上書きするキー・バリュー。

	Returns:
		username、email、password、password_confirm、名前（日本語・かな）、birth_date を含む辞書。
	"""
	payload: dict[str, object] = {
		"username": "taro_01",
		"email": "taro@example.com",
		"password": "Password1!",
		"password_confirm": "Password1!",
		"last_name": "山田",
		"first_name": "太郎",
		"last_name_kana": "ヤマダ",
		"first_name_kana": "タロウ",
		"birth_date": date(1995, 4, 1),
	}
	payload.update(overrides)
	return payload


def _email_of_length(length: int) -> str:
	"""
	メールアドレスの長さテストのため、指定文字数のメールアドレスを生成。

	Args:
		length: 生成するメールアドレスの合計文字数。

	Returns:
		指定文字数のメールアドレス文字列（形式: local_part@domain）。
	"""
	local_part = "a" * 64
	domain_middle_length = length - 197
	return f"{local_part}@{'a' * 63}.{'b' * 63}.{'c' * domain_middle_length}.com"


def test_register_request_accepts_valid_payload() -> None:
	"""
	RegisterRequest がすべての必須フィールドを持つ有効なペイロードを受け入れることを検証。

	条件：ユーザー名、メール、パスワード（確認付き）、名前（日本語・かな）、生年月日を含む有効なペイロードでリクエストを作成したとき、フィールドが正しく保持されること。
	"""
	payload = RegisterRequest(**_register_payload())

	assert payload.username == "taro_01"
	assert payload.birth_date == date(1995, 4, 1)


@pytest.mark.parametrize("model", [RegisterRequest, ResendVerifyEmailRequest, PasswordForgotRequest])
def test_email_requests_accept_254_characters(model: type[object]) -> None:
	"""
	RegisterRequest、ResendVerifyEmailRequest、PasswordForgotRequest が254文字のメールアドレスを受け入れることを検証。

	条件：各リクエストスキーマで254文字のメールアドレスを入力したとき、バリデーションが通り、メール長が254であること。
	"""
	email = _email_of_length(254)
	if model is RegisterRequest:
		request = model(**_register_payload(email=email))
	else:
		request = model(email=email)

	assert len(request.email) == 254


@pytest.mark.parametrize("model", [RegisterRequest, ResendVerifyEmailRequest, PasswordForgotRequest])
def test_email_requests_reject_255_characters(model: type[object]) -> None:
	"""
	RegisterRequest、ResendVerifyEmailRequest、PasswordForgotRequest が255文字以上のメールアドレスを拒否することを検証。

	条件：各リクエストスキーマで255文字のメールアドレスを入力したとき、ValidationError が送出されること。
	"""
	email = _email_of_length(255)
	if model is RegisterRequest:
		payload = _register_payload(email=email)
	else:
		payload = {"email": email}

	with pytest.raises(ValidationError):
		model(**payload)


def test_login_request_accepts_254_character_email() -> None:
	"""
	LoginRequest が254文字のメールアドレスを identifier として受け入れることを検証。

	条件：254文字のメールアドレスを identifier に設定したLoginRequest を作成したとき、長さが254であること。
	"""
	request = LoginRequest(identifier=_email_of_length(254), password="password")

	assert len(request.identifier) == 254


def test_login_request_rejects_255_character_email() -> None:
	"""
	LoginRequest が255文字以上のメールアドレスを identifier として拒否することを検証。

	条件：255文字のメールアドレスを identifier に設定してLoginRequest を作成したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		LoginRequest(identifier=_email_of_length(255), password="password")


@pytest.mark.parametrize(
	"field,value",
	[
		("username", "ab"),
		("username", "a" * 51),
		("username", "taro@example.com"),
		("email", "not-an-email"),
		("email", _email_of_length(255)),
		("last_name", ""),
		("last_name", "a" * 31),
		("first_name", ""),
		("first_name_kana", "タロa"),
	],
)
def test_register_request_rejects_invalid_field(field: str, value: object) -> None:
	"""
	RegisterRequest が不正なフィールド値を拒否することを検証。

	条件：username（短すぎる、長すぎる、メール形式）、email（不正形式、長すぎる）、last_name/first_name（空、長すぎる）、first_name_kana（非日本語かな混合）のいずれかの不正値を入力したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(**{field: value}))


@pytest.mark.parametrize("password", ["password", "PASSWORD", "12345678", "!!!!!!!!"])
def test_register_request_requires_two_password_character_categories(password: str) -> None:
	"""
	RegisterRequest がパスワードに少なくとも2種類の文字種（英大文字、英小文字、数字、記号）を必須とすることを検証。

	条件：小文字のみ、大文字のみ、数字のみ、記号のみのいずれかで構成されたパスワードを入力したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(password=password, password_confirm=password))


def test_register_request_rejects_password_mismatch() -> None:
	"""
	RegisterRequest がパスワードと確認用パスワードの不一致を拒否することを検証。

	条件：password と password_confirm が異なる値のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(password_confirm="Password2!"))


def test_register_request_rejects_future_birth_date() -> None:
	"""
	RegisterRequest が未来の日付を birth_date として拒否することを検証。

	条件：明日の日付を birth_date に設定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(birth_date=date.today() + timedelta(days=1)))


def test_register_response_has_uuid_email_and_message() -> None:
	"""
	RegisterResponse が id（UUID）、email、message フィールドを持つことを検証。

	条件：UUID、メールアドレス、メッセージを指定して RegisterResponse を作成したとき、各フィールドが正しく保持されること。
	"""
	response = RegisterResponse(id=uuid4(), email="taro@example.com", message="確認メールを送信しました。")

	assert response.email == "taro@example.com"


def test_login_request_accepts_identifier_and_password() -> None:
	"""
	LoginRequest が identifier（ユーザー名またはメール）と password を受け入れることを検証。

	条件：identifier と password を指定してLoginRequest を作成したとき、フィールドが正しく保持されること。
	"""
	request = LoginRequest(identifier="taro_01", password="old-password")

	assert request.identifier == "taro_01"


def test_password_inputs_accept_128_unicode_code_points_and_reject_129() -> None:
	"""
	パスワード入力が128文字（Unicodeコードポイント）を受け入れ、129文字以上を拒否することを検証。

	条件：129文字のUnicodeを含むパスワード（英記号と日本語）でRegisterRequest を作成したとき成功し、130文字のパスワードでは ValidationError が送出されること。
	"""
	password = "A1!" + "あ" * 125
	assert len(password) == 128
	assert RegisterRequest(**_register_payload(password=password, password_confirm=password)).password == password

	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(password=password + "あ", password_confirm=password + "あ"))


@pytest.mark.parametrize("model,field", [(LoginRequest, "password"), (PasswordResetRequest, "new_password")])
def test_password_input_limits_apply_before_auth_service(model: type[object], field: str) -> None:
	"""
	パスワード入力制限（最大128文字）が認証サービス処理より前のスキーマバリデーション段階で適用されることを検証。

	条件：129文字を超えるパスワードを LoginRequest または PasswordResetRequest に設定したとき、ValidationError が送出されること。
	"""
	password = "A1!" + "a" * 126
	if model is LoginRequest:
		payload = {"identifier": "taro", "password": password}
	else:
		payload = _password_reset_payload(new_password=password, password_confirm=password)

	with pytest.raises(ValidationError):
		model(**payload)


@pytest.mark.parametrize("field,value", [("identifier", ""), ("identifier", _email_of_length(255)), ("password", "")])
def test_login_request_rejects_invalid_field(field: str, value: object) -> None:
	"""
	LoginRequest が不正なフィールド値（identifier またはpassword）を拒否することを検証。

	条件：identifier（空または255文字超）またはpassword（空）の不正値を入力したとき、ValidationError が送出されること。
	"""
	payload: dict[str, object] = {"identifier": "taro", "password": "password"}
	payload[field] = value

	with pytest.raises(ValidationError):
		LoginRequest(**payload)


def test_login_response_accepts_bearer_response() -> None:
	"""
	LoginResponse が bearer token_type を受け入れることを検証。

	条件：token_type="bearer" を含むLoginResponse を作成したとき、フィールドが正しく保持されること。
	"""
	response = LoginResponse(access_token="signed-token", token_type="bearer", expires_in=900)

	assert response.token_type == "bearer"


def test_login_response_rejects_non_bearer_token_type() -> None:
	"""
	LoginResponse が bearer 以外の token_type（例："basic"）を拒否することを検証。

	条件：token_type="basic" を指定してLoginResponse を作成したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		LoginResponse(access_token="signed-token", token_type="basic", expires_in=900)


def test_me_response_accepts_optional_profile_and_restricted_literals() -> None:
	"""
	MeResponse がオプショナルなプロファイルフィールド（名前・生年月日など）と制限されたリテラル値（role、auth_mode）を受け入れることを検証。

	条件：プロファイル情報が None、role="member"、auth_mode="jwt" を指定してMeResponse を作成したとき、フィールドが正しく保持されること。
	"""
	response = MeResponse(
		id=uuid4(),
		username="taro_01",
		email="taro@example.com",
		last_name=None,
		first_name=None,
		last_name_kana=None,
		first_name_kana=None,
		birth_date=None,
		profile_completed=False,
		role="member",
		has_password=False,
		oauth_providers=[],
		auth_mode="jwt",
	)

	assert response.profile_completed is False


def test_auth_config_response_accepts_supported_auth_mode() -> None:
	"""
	AuthConfigResponse がサポート対象の auth_mode（"session"）を受け入れることを検証。

	条件：auth_mode="session"、google_login_enabled=True を指定してAuthConfigResponse を作成したとき、フィールドが正しく保持されること。
	"""
	response = AuthConfigResponse(auth_mode="session", google_login_enabled=True, csrf_cookie_name="cerberus_csrf")

	assert response.auth_mode == "session"


def test_auth_config_response_rejects_unknown_auth_mode() -> None:
	"""
	AuthConfigResponse が未知の auth_mode（例："cookie"）を拒否することを検証。

	条件：auth_mode="cookie" を指定してAuthConfigResponse を作成したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		AuthConfigResponse(auth_mode="cookie", google_login_enabled=False, csrf_cookie_name="csrf")


def test_refresh_response_accepts_bearer_response() -> None:
	"""
	RefreshResponse が bearer token_type を受け入れることを検証。

	条件：token_type="bearer" を含むRefreshResponse を作成したとき、フィールドが正しく保持されること。
	"""
	response = RefreshResponse(access_token="rotated-token", token_type="bearer", expires_in=900)

	assert response.access_token == "rotated-token"


def test_refresh_response_rejects_non_bearer_token_type() -> None:
	"""
	RefreshResponse が bearer 以外の token_type（例："basic"）を拒否することを検証。

	条件：token_type="basic" を指定してRefreshResponse を作成したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		RefreshResponse(access_token="rotated-token", token_type="basic", expires_in=900)


def test_verify_email_request_accepts_token() -> None:
	"""
	VerifyEmailRequest がメール検証トークンを受け入れることを検証。

	条件：token フィールドにメール検証トークン文字列を指定してVerifyEmailRequest を作成したとき、フィールドが正しく保持されること。
	"""
	request = VerifyEmailRequest(token="email-verification-token")

	assert request.token == "email-verification-token"


def test_verify_email_token_accepts_512_code_points_and_rejects_513() -> None:
	"""
	VerifyEmailRequest のトークンが512文字（Unicodeコードポイント）を受け入れ、513文字以上を拒否することを検証。

	条件：512文字のトークンは成功し、513文字のトークンでは ValidationError が送出されること。
	"""
	assert VerifyEmailRequest(token="a" * 512).token == "a" * 512
	with pytest.raises(ValidationError):
		VerifyEmailRequest(token="a" * 513)


def test_schema_limits_follow_backend_environment_settings(monkeypatch: pytest.MonkeyPatch) -> None:
	"""
	スキーマのフィールド制限がバックエンド環境設定（PASSWORD_MAX_LENGTH、AUTH_TOKEN_MAX_LENGTH）に従うことを検証。

	条件：PASSWORD_MAX_LENGTH=8、AUTH_TOKEN_MAX_LENGTH=1に変更したとき、これらの制限を超えるパスワード・トークンは ValidationError が送出されること。
	"""
	monkeypatch.setenv("PASSWORD_MAX_LENGTH", "8")
	monkeypatch.setenv("AUTH_TOKEN_MAX_LENGTH", "1")
	get_backend_settings.cache_clear()

	with pytest.raises(ValidationError):
		LoginRequest(identifier="taro", password="Password1!")
	with pytest.raises(ValidationError):
		VerifyEmailRequest(token="ab")


def test_oauth_query_and_exchange_code_reject_513_code_points() -> None:
	"""
	OAuthCallbackQuery と OAuthExchangeRequest の code フィールドが513文字以上を拒否することを検証。

	条件：513文字の code を OAuthCallbackQuery または OAuthExchangeRequest に設定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		OAuthCallbackQuery(code="a" * 513)
	with pytest.raises(ValidationError):
		OAuthExchangeRequest(code="a" * 513)


@pytest.mark.parametrize("payload", [{}, {"token": ""}])
def test_verify_email_request_rejects_missing_or_empty_token(payload: dict[str, object]) -> None:
	"""
	VerifyEmailRequest が token フィールド欠落または空値を拒否することを検証。

	条件：token フィールドがない、または空文字列のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		VerifyEmailRequest(**payload)


def test_resend_verify_email_request_and_response_accept_valid_values() -> None:
	"""
	ResendVerifyEmailRequest と ResendVerifyEmailResponse が有効なメールアドレス・メッセージを受け入れることを検証。

	条件：有効なメールアドレスとメッセージを指定したとき、フィールドが正しく保持されること。
	"""
	request = ResendVerifyEmailRequest(email="taro@example.com")
	response = ResendVerifyEmailResponse(message="確認メールを送信しました。")

	assert request.email == "taro@example.com"
	assert response.message == "確認メールを送信しました。"


@pytest.mark.parametrize("email", ["", "not-an-email", _email_of_length(255)])
def test_resend_verify_email_request_rejects_invalid_email(email: str) -> None:
	"""
	ResendVerifyEmailRequest が不正なメールアドレス（空、形式不正、長すぎる）を拒否することを検証。

	条件：空、メール形式でない、255文字超のメールアドレスを入力したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		ResendVerifyEmailRequest(email=email)


def test_password_forgot_request_and_response_accept_valid_values() -> None:
	"""
	PasswordForgotRequest と PasswordForgotResponse が有効なメールアドレス・メッセージを受け入れることを検証。

	条件：有効なメールアドレスとメッセージを指定したとき、フィールドが正しく保持されること。
	"""
	request = PasswordForgotRequest(email="taro@example.com")
	response = PasswordForgotResponse(message="再設定用メールを送信しました。")

	assert request.email == "taro@example.com"
	assert response.message == "再設定用メールを送信しました。"


@pytest.mark.parametrize("email", ["", "not-an-email", _email_of_length(255)])
def test_password_forgot_request_rejects_invalid_email(email: str) -> None:
	"""
	PasswordForgotRequest が不正なメールアドレス（空、形式不正、長すぎる）を拒否することを検証。

	条件：空、メール形式でない、255文字超のメールアドレスを入力したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		PasswordForgotRequest(email=email)


def _password_reset_payload(**overrides: object) -> dict[str, object]:
	"""
	PasswordResetRequest テストのためのベースペイロードを生成。

	Args:
		**overrides: ベースペイロードの指定フィールドを上書きするキー・バリュー。

	Returns:
		token、new_password、password_confirm を含む辞書。
	"""
	payload: dict[str, object] = {
		"token": "password-reset-token",
		"new_password": "NewPassword1!",
		"password_confirm": "NewPassword1!",
	}
	payload.update(overrides)
	return payload


def test_password_reset_request_accepts_valid_payload() -> None:
	"""
	PasswordResetRequest がすべての必須フィールド（token、new_password、password_confirm）を持つ有効なペイロードを受け入れることを検証。

	条件：有効なtoken、一致するパスワードを指定したとき、フィールドが正しく保持されること。
	"""
	request = PasswordResetRequest(**_password_reset_payload())

	assert request.token == "password-reset-token"


@pytest.mark.parametrize(
	"payload",
	[
		{"token": ""},
		{"new_password": "password", "password_confirm": "password"},
		{"new_password": "PASSWORD", "password_confirm": "PASSWORD"},
		{"new_password": "12345678", "password_confirm": "12345678"},
		{"new_password": "!!!!!!!!", "password_confirm": "!!!!!!!!"},
	],
)
def test_password_reset_request_rejects_invalid_values(payload: dict[str, object]) -> None:
	"""
	PasswordResetRequest が不正な値（空token、文字種1種のパスワード）を拒否することを検証。

	条件：token が空、またはパスワードが1種類の文字種（小文字のみ、大文字のみ、数字のみ、記号のみ）のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		PasswordResetRequest(**_password_reset_payload(**payload))


def test_password_reset_request_rejects_password_mismatch() -> None:
	"""
	PasswordResetRequest がパスワードと確認用パスワードの不一致を拒否することを検証。

	条件：new_password と password_confirm が異なる値のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		PasswordResetRequest(**_password_reset_payload(password_confirm="OtherPassword1!"))


def test_register_request_rejects_undefined_field() -> None:
	"""想定外の入力フィールドを拒否する（extra="forbid"）。"""
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(is_admin=True))


def test_login_request_rejects_undefined_field() -> None:
	"""
	LoginRequest が予期しないフィールド（extra="forbid"）を拒否することを検証。

	条件：login_identifier や role など、LoginRequest の定義に無いフィールドを追加したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		LoginRequest(login_identifier="user", password="Password1!", role="admin")


def test_password_reset_request_rejects_undefined_field() -> None:
	"""
	PasswordResetRequest が予期しないフィールド（extra="forbid"）を拒否することを検証。

	条件：user_id など、PasswordResetRequest の定義に無いフィールドを追加したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		PasswordResetRequest(**_password_reset_payload(user_id=str(uuid4())))


@pytest.mark.parametrize(
	"model",
	[
		AuthConfigResponse,
		CurrentUser,
		LoginRequest,
		LoginResponse,
		MeResponse,
		PasswordForgotRequest,
		PasswordForgotResponse,
		PasswordResetRequest,
		RefreshResponse,
		RegisterRequest,
		RegisterResponse,
		ResendVerifyEmailRequest,
		ResendVerifyEmailResponse,
		VerifyEmailRequest,
	],
)
def test_auth_schemas_forbid_extra_fields(model: type[StrictSchema]) -> None:
	"""
	auth系すべてのDTOが StrictSchema を継承し、extra="forbid" が有効であることを検証。

	条件：各スキーマモデルが StrictSchema の subclass で、model_config の extra が "forbid" に設定されていること。
	"""
	"""auth系DTOが漏れなく共通基底を継承し、extra="forbid" が効いていること。"""
	assert issubclass(model, StrictSchema)
	assert model.model_config.get("extra") == "forbid"

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
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
from pydantic import ValidationError


def _register_payload(**overrides: object) -> dict[str, object]:
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


def test_register_request_accepts_valid_payload() -> None:
	payload = RegisterRequest(**_register_payload())

	assert payload.username == "taro_01"
	assert payload.birth_date == date(1995, 4, 1)


@pytest.mark.parametrize(
	"field,value",
	[
		("username", "ab"),
		("username", "a" * 51),
		("username", "taro@example.com"),
		("email", "not-an-email"),
		("email", "taro@example.com" + "a" * 40),
		("last_name", ""),
		("last_name", "a" * 31),
		("first_name", ""),
		("first_name_kana", "タロa"),
	],
)
def test_register_request_rejects_invalid_field(field: str, value: object) -> None:
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(**{field: value}))


@pytest.mark.parametrize("password", ["password", "PASSWORD", "12345678", "!!!!!!!!"])
def test_register_request_requires_two_password_character_categories(password: str) -> None:
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(password=password, password_confirm=password))


def test_register_request_rejects_password_mismatch() -> None:
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(password_confirm="Password2!"))


def test_register_request_rejects_future_birth_date() -> None:
	with pytest.raises(ValidationError):
		RegisterRequest(**_register_payload(birth_date=date.today() + timedelta(days=1)))


def test_register_response_has_uuid_email_and_message() -> None:
	response = RegisterResponse(id=uuid4(), email="taro@example.com", message="確認メールを送信しました。")

	assert response.email == "taro@example.com"


def test_login_request_accepts_identifier_and_password() -> None:
	request = LoginRequest(identifier="taro_01", password="old-password")

	assert request.identifier == "taro_01"


@pytest.mark.parametrize("field,value", [("identifier", ""), ("identifier", "a" * 51), ("password", "")])
def test_login_request_rejects_invalid_field(field: str, value: object) -> None:
	payload: dict[str, object] = {"identifier": "taro", "password": "password"}
	payload[field] = value

	with pytest.raises(ValidationError):
		LoginRequest(**payload)


def test_login_response_accepts_bearer_response() -> None:
	response = LoginResponse(access_token="signed-token", token_type="bearer", expires_in=900)

	assert response.token_type == "bearer"


def test_login_response_rejects_non_bearer_token_type() -> None:
	with pytest.raises(ValidationError):
		LoginResponse(access_token="signed-token", token_type="basic", expires_in=900)


def test_me_response_accepts_optional_profile_and_restricted_literals() -> None:
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
	response = AuthConfigResponse(auth_mode="session", google_login_enabled=True, csrf_cookie_name="cerberus_csrf")

	assert response.auth_mode == "session"


def test_auth_config_response_rejects_unknown_auth_mode() -> None:
	with pytest.raises(ValidationError):
		AuthConfigResponse(auth_mode="cookie", google_login_enabled=False, csrf_cookie_name="csrf")


def test_refresh_response_accepts_bearer_response() -> None:
	response = RefreshResponse(access_token="rotated-token", token_type="bearer", expires_in=900)

	assert response.access_token == "rotated-token"


def test_refresh_response_rejects_non_bearer_token_type() -> None:
	with pytest.raises(ValidationError):
		RefreshResponse(access_token="rotated-token", token_type="basic", expires_in=900)


def test_verify_email_request_accepts_token() -> None:
	request = VerifyEmailRequest(token="email-verification-token")

	assert request.token == "email-verification-token"


@pytest.mark.parametrize("payload", [{}, {"token": ""}])
def test_verify_email_request_rejects_missing_or_empty_token(payload: dict[str, object]) -> None:
	with pytest.raises(ValidationError):
		VerifyEmailRequest(**payload)


def test_resend_verify_email_request_and_response_accept_valid_values() -> None:
	request = ResendVerifyEmailRequest(email="taro@example.com")
	response = ResendVerifyEmailResponse(message="確認メールを送信しました。")

	assert request.email == "taro@example.com"
	assert response.message == "確認メールを送信しました。"


@pytest.mark.parametrize("email", ["", "not-an-email", "taro@example.com" + "a" * 40])
def test_resend_verify_email_request_rejects_invalid_email(email: str) -> None:
	with pytest.raises(ValidationError):
		ResendVerifyEmailRequest(email=email)


def test_password_forgot_request_and_response_accept_valid_values() -> None:
	request = PasswordForgotRequest(email="taro@example.com")
	response = PasswordForgotResponse(message="再設定用メールを送信しました。")

	assert request.email == "taro@example.com"
	assert response.message == "再設定用メールを送信しました。"


@pytest.mark.parametrize("email", ["", "not-an-email", "taro@example.com" + "a" * 40])
def test_password_forgot_request_rejects_invalid_email(email: str) -> None:
	with pytest.raises(ValidationError):
		PasswordForgotRequest(email=email)


def _password_reset_payload(**overrides: object) -> dict[str, object]:
	payload: dict[str, object] = {
		"token": "password-reset-token",
		"new_password": "NewPassword1!",
		"password_confirm": "NewPassword1!",
	}
	payload.update(overrides)
	return payload


def test_password_reset_request_accepts_valid_payload() -> None:
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
	with pytest.raises(ValidationError):
		PasswordResetRequest(**_password_reset_payload(**payload))


def test_password_reset_request_rejects_password_mismatch() -> None:
	with pytest.raises(ValidationError):
		PasswordResetRequest(**_password_reset_payload(password_confirm="OtherPassword1!"))


@pytest.mark.parametrize(
	"model,payload",
	[
		(RegisterRequest, _register_payload()),
		(RegisterResponse, {"id": uuid4(), "email": "taro@example.com", "message": "ok"}),
		(LoginRequest, {"identifier": "taro", "password": "password"}),
		(LoginResponse, {"access_token": "token", "token_type": "bearer", "expires_in": 900}),
		(RefreshResponse, {"access_token": "token", "token_type": "bearer", "expires_in": 900}),
		(VerifyEmailRequest, {"token": "token"}),
		(ResendVerifyEmailRequest, {"email": "taro@example.com"}),
		(ResendVerifyEmailResponse, {"message": "ok"}),
		(PasswordForgotRequest, {"email": "taro@example.com"}),
		(PasswordForgotResponse, {"message": "ok"}),
		(PasswordResetRequest, _password_reset_payload()),
		(
			MeResponse,
			{
				"id": uuid4(),
				"username": "taro",
				"email": "taro@example.com",
				"last_name": None,
				"first_name": None,
				"last_name_kana": None,
				"first_name_kana": None,
				"birth_date": None,
				"profile_completed": False,
				"role": "member",
				"has_password": True,
				"oauth_providers": [],
				"auth_mode": "session",
			},
		),
		(AuthConfigResponse, {"auth_mode": "session", "google_login_enabled": True, "csrf_cookie_name": "csrf"}),
	],
)
def test_auth_schemas_reject_extra_fields(model: type[object], payload: dict[str, object]) -> None:
	payload["unexpected"] = "rejected"

	with pytest.raises(ValidationError):
		model(**payload)  # type: ignore[call-arg]


def test_current_user_accepts_database_authentication_state() -> None:
	user = CurrentUser(
		id=uuid4(),
		username="taro",
		role="member",
		is_active=True,
		email_verified_at=datetime.now(timezone.utc),
	)

	assert user.is_active is True


def test_current_user_rejects_extra_fields() -> None:
	with pytest.raises(ValidationError):
		CurrentUser(
			id=uuid4(),
			username="taro",
			role="member",
			is_active=True,
			email_verified_at=None,
			unexpected="rejected",
		)

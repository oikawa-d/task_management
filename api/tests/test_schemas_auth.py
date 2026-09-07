from datetime import date, timedelta
from uuid import uuid4

import pytest
from app.schemas.auth import (
	AuthConfigResponse,
	LoginRequest,
	LoginResponse,
	MeResponse,
	RegisterRequest,
	RegisterResponse,
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

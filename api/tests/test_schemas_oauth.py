import pytest
from app.schemas.oauth import (
	OAuthCallbackResult,
	OAuthExchangeRequest,
	OAuthExchangeResponse,
	OAuthStartResult,
)
from pydantic import ValidationError


def test_oauth_start_result_accepts_authorize_url_and_state() -> None:
	result = OAuthStartResult(
		authorize_url="https://accounts.google.com/o/oauth2/v2/auth?state=state-token",
		state="state-token",
	)

	assert result.state == "state-token"


def test_oauth_callback_result_accepts_session_mode_without_handoff_code() -> None:
	result = OAuthCallbackResult(auth_mode="session", redirect_to="/dashboard")

	assert result.handoff_code is None


def test_oauth_callback_result_accepts_jwt_mode_with_handoff_code() -> None:
	result = OAuthCallbackResult(
		auth_mode="jwt",
		redirect_to="/projects/1",
		handoff_code="handoff-token",
	)

	assert result.handoff_code == "handoff-token"


@pytest.mark.parametrize("auth_mode", ["cookie", "oauth", ""])
def test_oauth_callback_result_rejects_unknown_auth_mode(auth_mode: str) -> None:
	with pytest.raises(ValidationError):
		OAuthCallbackResult(auth_mode=auth_mode, redirect_to="/dashboard")


def test_oauth_exchange_request_accepts_handoff_code() -> None:
	payload = OAuthExchangeRequest(code="handoff-token")

	assert payload.code == "handoff-token"


@pytest.mark.parametrize("code", ["", None])
def test_oauth_exchange_request_rejects_empty_or_missing_code(code: object) -> None:
	with pytest.raises(ValidationError):
		OAuthExchangeRequest(code=code)


def test_oauth_exchange_response_accepts_bearer_token_and_redirect_to() -> None:
	response = OAuthExchangeResponse(
		access_token="access-token",
		token_type="bearer",
		expires_in=900,
		redirect_to="/dashboard",
	)

	assert response.redirect_to == "/dashboard"


def test_oauth_exchange_response_rejects_non_bearer_token_type() -> None:
	with pytest.raises(ValidationError):
		OAuthExchangeResponse(
			access_token="access-token",
			token_type="basic",
			expires_in=900,
			redirect_to="/dashboard",
		)


@pytest.mark.parametrize(
	"field,value",
	[
		("authorize_url", ""),
		("state", ""),
		("redirect_to", ""),
		("code", ""),
		("access_token", ""),
		("expires_in", 0),
	],
)
def test_oauth_schemas_reject_invalid_required_values(field: str, value: object) -> None:
	start_payload = {
		"authorize_url": "https://accounts.google.com/auth",
		"state": "state-token",
	}
	callback_payload = {"auth_mode": "session", "redirect_to": "/dashboard"}
	exchange_request_payload = {"code": "handoff-token"}
	exchange_response_payload = {
		"access_token": "access-token",
		"token_type": "bearer",
		"expires_in": 900,
		"redirect_to": "/dashboard",
	}

	payloads = {
		"authorize_url": (OAuthStartResult, start_payload),
		"state": (OAuthStartResult, start_payload),
		"redirect_to": (OAuthCallbackResult, callback_payload),
		"code": (OAuthExchangeRequest, exchange_request_payload),
		"access_token": (OAuthExchangeResponse, exchange_response_payload),
		"expires_in": (OAuthExchangeResponse, exchange_response_payload),
	}
	model, payload = payloads[field]
	payload[field] = value

	with pytest.raises(ValidationError):
		model(**payload)

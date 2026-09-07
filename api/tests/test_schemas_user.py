from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.schemas.user import (
	LoginHistoryItem,
	LoginHistoryListResponse,
	LoginHistoryMeta,
	PasswordChangeRequest,
	UserProfileResponse,
	UserProfileUpdateRequest,
)
from pydantic import ValidationError


def test_user_profile_response_accepts_incomplete_profile() -> None:
	response = UserProfileResponse(
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
	)

	assert response.profile_completed is False
	assert "auth_mode" not in response.model_dump()


def test_user_profile_update_tracks_explicit_null_as_set() -> None:
	payload = UserProfileUpdateRequest(last_name=None)

	assert payload.model_fields_set == {"last_name"}
	assert payload.model_dump(exclude_unset=True) == {"last_name": None}


@pytest.mark.parametrize(
	"field,value",
	[
		("last_name", ""),
		("last_name", "a" * 31),
		("first_name_kana", "タロa"),
		("first_name_kana", ""),
		("birth_date", date.today() + timedelta(days=1)),
	],
)
def test_user_profile_update_rejects_invalid_values(field: str, value: object) -> None:
	with pytest.raises(ValidationError):
		UserProfileUpdateRequest(**{field: value})


def test_user_profile_update_accepts_valid_profile_values() -> None:
	payload = UserProfileUpdateRequest(
		last_name="山田",
		first_name="太郎",
		last_name_kana="ヤマダ",
		first_name_kana="タロウ",
		birth_date=date(1995, 4, 1),
	)

	assert payload.birth_date == date(1995, 4, 1)


def test_password_change_accepts_optional_current_password() -> None:
	payload = PasswordChangeRequest(new_password="Password1!", password_confirm="Password1!")

	assert payload.current_password is None


@pytest.mark.parametrize("password", ["password", "PASSWORD", "12345678", "!!!!!!!!"])
def test_password_change_requires_two_password_categories(password: str) -> None:
	with pytest.raises(ValidationError):
		PasswordChangeRequest(new_password=password, password_confirm=password)


def test_password_change_rejects_mismatched_confirmation() -> None:
	with pytest.raises(ValidationError):
		PasswordChangeRequest(new_password="Password1!", password_confirm="Password2!")


def test_login_history_response_excludes_login_identifier() -> None:
	created_at = datetime(2026, 9, 4, 1, tzinfo=timezone.utc)
	item = LoginHistoryItem(
		id=uuid4(),
		login_method="session",
		ip_address="203.0.113.10",
		user_agent="Mozilla/5.0",
		success=True,
		failure_reason=None,
		created_at=created_at,
	)
	response = LoginHistoryListResponse(items=[item], meta=LoginHistoryMeta(limit=50, count=1))

	assert response.meta.count == 1
	assert "login_identifier" not in item.model_dump()


@pytest.mark.parametrize("login_method", ["invalid", "oauth"])
def test_login_history_item_rejects_unknown_login_method(login_method: str) -> None:
	with pytest.raises(ValidationError):
		LoginHistoryItem(
			id=uuid4(),
			login_method=login_method,
			success=False,
			created_at=datetime.now(timezone.utc),
		)


@pytest.mark.parametrize(
	"field,value",
	[("limit", 0), ("count", -1)],
)
def test_login_history_meta_rejects_negative_counts(field: str, value: int) -> None:
	with pytest.raises(ValidationError):
		LoginHistoryMeta(**{field: value})

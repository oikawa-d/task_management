"""
ユーザープロフィール・パスワード変更・ログイン履歴スキーマのバリデーションを検証するテスト。
"""

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
	"""
	UserProfileResponse がプロフィール情報が不完全（名前・生年月日がNone）なケースを受け入れることを検証。

	条件：optional フィールド（last_name、first_name など）が None で、profile_completed=False のとき、response が正しく構築され、auth_mode フィールドが含まれないこと。
	"""
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
	"""
	UserProfileUpdateRequest が explicit null と unset フィールドを区別し、model_fields_set に記録することを検証。

	条件：last_name=None を明示的に指定したとき、model_fields_set に "last_name" が含まれ、model_dump(exclude_unset=True) で {"last_name": None} が返されること。
	"""
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
	"""
	UserProfileUpdateRequest が不正なプロフィール値（空、長すぎる、混合字種、未来日付）を拒否することを検証。

	条件：各パターンの不正値を指定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		UserProfileUpdateRequest(**{field: value})


def test_user_profile_update_accepts_valid_profile_values() -> None:
	"""
	UserProfileUpdateRequest が有効なプロフィール値（名前、生年月日など）を受け入れることを検証。

	条件：すべてのプロフィールフィールドを指定してUserProfileUpdateRequest を作成したとき、各フィールドが正しく保持されること。
	"""
	payload = UserProfileUpdateRequest(
		last_name="山田",
		first_name="太郎",
		last_name_kana="ヤマダ",
		first_name_kana="タロウ",
		birth_date=date(1995, 4, 1),
	)

	assert payload.birth_date == date(1995, 4, 1)


def test_password_change_accepts_optional_current_password() -> None:
	"""
	PasswordChangeRequest が optional current_password を受け入れることを検証。

	条件：current_password を指定せず new_password のみ指定したとき、current_password が None に保たれること。
	"""
	payload = PasswordChangeRequest(new_password="Password1!", password_confirm="Password1!")

	assert payload.current_password is None


def test_password_change_rejects_password_fields_over_128_unicode_code_points() -> None:
	"""
	PasswordChangeRequest がパスワードフィールドの128文字（Unicodeコードポイント）制限を検証することを検証。

	条件：new_password または current_password が129文字超のとき、ValidationError が送出されること。
	"""
	password = "A1!" + "a" * 126
	with pytest.raises(ValidationError):
		PasswordChangeRequest(new_password=password, password_confirm=password)
	with pytest.raises(ValidationError):
		PasswordChangeRequest(current_password=password, new_password="Password1!", password_confirm="Password1!")


@pytest.mark.parametrize("password", ["password", "PASSWORD", "12345678", "!!!!!!!!"])
def test_password_change_requires_two_password_categories(password: str) -> None:
	"""
	PasswordChangeRequest が new_password に少なくとも2種類の文字種を必須とすることを検証。

	条件：1種類の文字種（小文字、大文字、数字、記号のいずれか1つ）のみのパスワードを入力したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		PasswordChangeRequest(new_password=password, password_confirm=password)


def test_password_change_rejects_mismatched_confirmation() -> None:
	"""
	PasswordChangeRequest がパスワード確認用パスワードの不一致を拒否することを検証。

	条件：new_password と password_confirm が異なる値のとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		PasswordChangeRequest(new_password="Password1!", password_confirm="Password2!")


def test_login_history_response_excludes_login_identifier() -> None:
	"""
	LoginHistoryItem がセキュリティのため login_identifier フィールドを response に含まないことを検証。

	条件：LoginHistoryItem を model_dump() したとき、login_identifier キーが含まれないこと。
	"""
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
	"""
	LoginHistoryItem が unknown login_method を拒否することを検証。

	条件：login_method="invalid" または "oauth" など、定義外の値を指定したとき、ValidationError が送出されること。
	"""
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
	"""
	LoginHistoryMeta が limit=0 または count が負の値を拒否することを検証。

	条件：limit または count に 0 以下の値を指定したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		LoginHistoryMeta(**{field: value})

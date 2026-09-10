import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.exceptions import InvalidCredentialsError, NotFoundError, ServiceUnavailableError, ValidationError
from app.repository import login_history_repository, oauth_account_repository, redis_store, user_repository
from app.schemas.auth import CurrentUser
from app.schemas.user import PasswordChangeRequest, UserProfileUpdateRequest
from app.service import user_service


def _current_user(user_id: uuid.UUID) -> CurrentUser:
	return CurrentUser(id=user_id, username="taro", role="member", is_active=True, email_verified_at=None)


def _fake_user(**overrides: object) -> SimpleNamespace:
	defaults = {
		"id": uuid.uuid4(),
		"username": "taro",
		"email": "taro@example.com",
		"last_name": "山田",
		"first_name": "太郎",
		"last_name_kana": "ヤマダ",
		"first_name_kana": "タロウ",
		"birth_date": date(1995, 4, 1),
		"role": "member",
		"password_hash": "argon2-hash",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


def _fake_oauth_account(provider: str) -> SimpleNamespace:
	return SimpleNamespace(provider=provider)


def _fake_login_history(**overrides: object) -> SimpleNamespace:
	defaults = {
		"id": uuid.uuid4(),
		"login_method": "session",
		"ip_address": "203.0.113.10",
		"user_agent": "pytest",
		"success": True,
		"failure_reason": None,
		"created_at": "2026-09-03T04:05:06+00:00",
		"login_identifier": "taro",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


# --- get_profile -----------------------------------------------------------


async def test_get_profile_completed_true(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id)))
	monkeypatch.setattr(
		oauth_account_repository, "list_by_user_id", AsyncMock(return_value=[_fake_oauth_account("google")])
	)

	response = await user_service.get_profile(_current_user(user_id), db=object())

	assert response.profile_completed is True
	assert response.oauth_providers == ["google"]


async def test_get_profile_completed_false(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id, birth_date=None)))
	monkeypatch.setattr(oauth_account_repository, "list_by_user_id", AsyncMock(return_value=[]))

	response = await user_service.get_profile(_current_user(user_id), db=object())

	assert response.profile_completed is False


async def test_get_profile_not_found_raises(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=None))

	with pytest.raises(NotFoundError):
		await user_service.get_profile(_current_user(user_id), db=object())


async def test_get_profile_scoped_to_current_user_only(monkeypatch):
	user_id = uuid.uuid4()
	db_sentinel = object()
	get_by_id_mock = AsyncMock(return_value=_fake_user(id=user_id))
	monkeypatch.setattr(user_repository, "get_by_id", get_by_id_mock)
	monkeypatch.setattr(oauth_account_repository, "list_by_user_id", AsyncMock(return_value=[]))

	await user_service.get_profile(_current_user(user_id), db=db_sentinel)

	get_by_id_mock.assert_awaited_once_with(db_sentinel, user_id)


# --- update_profile ----------------------------------------------------------


async def test_update_profile_partial_update(monkeypatch):
	user_id = uuid.uuid4()
	existing = _fake_user(id=user_id, last_name="佐藤")
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=existing))
	update_mock = AsyncMock()
	monkeypatch.setattr(user_repository, "update_profile", update_mock)
	monkeypatch.setattr(oauth_account_repository, "list_by_user_id", AsyncMock(return_value=[]))

	payload = UserProfileUpdateRequest(last_name="鈴木")
	response = await user_service.update_profile(_current_user(user_id), payload, db=object())

	assert response.last_name == "鈴木"
	assert response.first_name == existing.first_name
	update_mock.assert_awaited_once()
	_, kwargs = update_mock.call_args
	assert kwargs["last_name"] == "鈴木"
	assert kwargs["first_name"] == existing.first_name


async def test_update_profile_null_rejected(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id)))
	payload = UserProfileUpdateRequest.model_construct(
		_fields_set={"last_name"},
		last_name=None,
		first_name=None,
		last_name_kana=None,
		first_name_kana=None,
		birth_date=None,
	)

	with pytest.raises(ValidationError):
		await user_service.update_profile(_current_user(user_id), payload, db=object())


async def test_update_profile_not_found_raises(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=None))

	with pytest.raises(NotFoundError):
		await user_service.update_profile(_current_user(user_id), UserProfileUpdateRequest(), db=object())


async def test_update_profile_completes_profile(monkeypatch):
	user_id = uuid.uuid4()
	existing = _fake_user(id=user_id, birth_date=None)
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=existing))
	monkeypatch.setattr(user_repository, "update_profile", AsyncMock())
	monkeypatch.setattr(oauth_account_repository, "list_by_user_id", AsyncMock(return_value=[]))

	payload = UserProfileUpdateRequest(birth_date=date(1995, 4, 1))
	response = await user_service.update_profile(_current_user(user_id), payload, db=object())

	assert response.profile_completed is True


async def test_update_profile_still_incomplete(monkeypatch):
	user_id = uuid.uuid4()
	existing = _fake_user(id=user_id, birth_date=None, last_name_kana=None)
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=existing))
	monkeypatch.setattr(user_repository, "update_profile", AsyncMock())
	monkeypatch.setattr(oauth_account_repository, "list_by_user_id", AsyncMock(return_value=[]))

	payload = UserProfileUpdateRequest(birth_date=date(1995, 4, 1))
	response = await user_service.update_profile(_current_user(user_id), payload, db=object())

	assert response.profile_completed is False


async def test_update_profile_updates_only_current_user(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id)))
	update_mock = AsyncMock()
	monkeypatch.setattr(user_repository, "update_profile", update_mock)
	monkeypatch.setattr(oauth_account_repository, "list_by_user_id", AsyncMock(return_value=[]))

	await user_service.update_profile(_current_user(user_id), UserProfileUpdateRequest(last_name="鈴木"), db=object())

	args, _ = update_mock.call_args
	assert args[1] == user_id


# --- change_password ---------------------------------------------------------


async def test_change_password_with_current_password_success(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(
		user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id, password_hash="old-hash"))
	)
	update_password_mock = AsyncMock()
	monkeypatch.setattr(user_repository, "update_password", update_password_mock)
	delete_sessions_mock = AsyncMock()
	revoke_refresh_mock = AsyncMock()
	monkeypatch.setattr(redis_store, "delete_all_sessions", delete_sessions_mock)
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", revoke_refresh_mock)

	payload = PasswordChangeRequest(
		current_password="OldPass1!", new_password="NewPass1!", password_confirm="NewPass1!"
	)
	await user_service.change_password(
		_current_user(user_id),
		payload,
		db=object(),
		verify_password=lambda plain, hashed: plain == "OldPass1!" and hashed == "old-hash",
		hash_password=lambda plain: f"hashed:{plain}",
	)

	update_password_mock.assert_awaited_once()
	args, _ = update_password_mock.call_args
	assert args[1] == user_id
	assert args[2] == "hashed:NewPass1!"
	delete_sessions_mock.assert_awaited_once_with(user_id)
	revoke_refresh_mock.assert_awaited_once_with(user_id)


async def test_change_password_wrong_current_password(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(
		user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id, password_hash="old-hash"))
	)
	update_password_mock = AsyncMock()
	monkeypatch.setattr(user_repository, "update_password", update_password_mock)
	delete_sessions_mock = AsyncMock()
	monkeypatch.setattr(redis_store, "delete_all_sessions", delete_sessions_mock)
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", AsyncMock())

	payload = PasswordChangeRequest(
		current_password="WrongPass1!", new_password="NewPass1!", password_confirm="NewPass1!"
	)

	with pytest.raises(InvalidCredentialsError):
		await user_service.change_password(
			_current_user(user_id),
			payload,
			db=object(),
			verify_password=lambda plain, hashed: False,
			hash_password=lambda plain: f"hashed:{plain}",
		)

	update_password_mock.assert_not_awaited()
	delete_sessions_mock.assert_not_awaited()


async def test_change_password_missing_current_password_when_required(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(
		user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id, password_hash="old-hash"))
	)

	payload = PasswordChangeRequest(current_password=None, new_password="NewPass1!", password_confirm="NewPass1!")

	with pytest.raises(ValidationError):
		await user_service.change_password(
			_current_user(user_id),
			payload,
			db=object(),
			verify_password=lambda plain, hashed: True,
			hash_password=lambda plain: plain,
		)


async def test_change_password_set_initial_password_without_current(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(
		user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id, password_hash=None))
	)
	update_password_mock = AsyncMock()
	monkeypatch.setattr(user_repository, "update_password", update_password_mock)
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock())
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", AsyncMock())

	payload = PasswordChangeRequest(current_password=None, new_password="NewPass1!", password_confirm="NewPass1!")
	await user_service.change_password(
		_current_user(user_id),
		payload,
		db=object(),
		verify_password=lambda plain, hashed: True,
		hash_password=lambda plain: f"hashed:{plain}",
	)

	update_password_mock.assert_awaited_once()


async def test_change_password_current_password_not_allowed_when_unset(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(
		user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id, password_hash=None))
	)

	payload = PasswordChangeRequest(
		current_password="Something1!", new_password="NewPass1!", password_confirm="NewPass1!"
	)

	with pytest.raises(ValidationError):
		await user_service.change_password(
			_current_user(user_id),
			payload,
			db=object(),
			verify_password=lambda plain, hashed: True,
			hash_password=lambda plain: plain,
		)


async def test_change_password_user_not_found_raises(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(user_repository, "get_by_id", AsyncMock(return_value=None))

	payload = PasswordChangeRequest(
		current_password="OldPass1!", new_password="NewPass1!", password_confirm="NewPass1!"
	)

	with pytest.raises(NotFoundError):
		await user_service.change_password(
			_current_user(user_id),
			payload,
			db=object(),
			verify_password=lambda plain, hashed: True,
			hash_password=lambda plain: plain,
		)


async def test_change_password_redis_failure_returns_service_unavailable_and_skips_db_update(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(
		user_repository, "get_by_id", AsyncMock(return_value=_fake_user(id=user_id, password_hash="old-hash"))
	)
	update_password_mock = AsyncMock()
	monkeypatch.setattr(user_repository, "update_password", update_password_mock)
	monkeypatch.setattr(redis_store, "delete_all_sessions", AsyncMock(side_effect=ConnectionError("redis down")))
	monkeypatch.setattr(redis_store, "revoke_all_refresh_tokens", AsyncMock())

	payload = PasswordChangeRequest(
		current_password="OldPass1!", new_password="NewPass1!", password_confirm="NewPass1!"
	)

	with pytest.raises(ServiceUnavailableError):
		await user_service.change_password(
			_current_user(user_id),
			payload,
			db=object(),
			verify_password=lambda plain, hashed: True,
			hash_password=lambda plain: f"hashed:{plain}",
		)

	update_password_mock.assert_not_awaited()


# --- get_login_history ---------------------------------------------------------


async def test_get_login_history_under_limit(monkeypatch):
	user_id = uuid.uuid4()
	histories = [_fake_login_history(), _fake_login_history(success=False, failure_reason="invalid_credentials")]
	list_mock = AsyncMock(return_value=histories)
	monkeypatch.setattr(login_history_repository, "list_by_user_id", list_mock)

	response = await user_service.get_login_history(_current_user(user_id), db=object(), limit=50)

	assert len(response.items) == 2
	assert response.meta.count == 2
	assert response.meta.limit == 50
	list_mock.assert_awaited_once()
	_, kwargs = list_mock.call_args
	assert kwargs == {"limit": 50, "offset": 0}


async def test_get_login_history_over_limit_truncated(monkeypatch):
	user_id = uuid.uuid4()
	histories = [_fake_login_history() for _ in range(50)]
	monkeypatch.setattr(login_history_repository, "list_by_user_id", AsyncMock(return_value=histories))

	response = await user_service.get_login_history(_current_user(user_id), db=object(), limit=50)

	assert len(response.items) == 50
	assert response.meta.count == 50
	assert response.meta.limit == 50


async def test_get_login_history_empty(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(login_history_repository, "list_by_user_id", AsyncMock(return_value=[]))

	response = await user_service.get_login_history(_current_user(user_id), db=object(), limit=50)

	assert response.items == []
	assert response.meta.count == 0


async def test_login_history_item_has_no_identifier(monkeypatch):
	user_id = uuid.uuid4()
	monkeypatch.setattr(login_history_repository, "list_by_user_id", AsyncMock(return_value=[_fake_login_history()]))

	response = await user_service.get_login_history(_current_user(user_id), db=object(), limit=50)

	dumped = response.items[0].model_dump()
	assert "login_identifier" not in dumped


async def test_get_login_history_scoped_to_current_user(monkeypatch):
	user_id = uuid.uuid4()
	list_mock = AsyncMock(return_value=[])
	monkeypatch.setattr(login_history_repository, "list_by_user_id", list_mock)

	await user_service.get_login_history(_current_user(user_id), db=object(), limit=50)

	args, _ = list_mock.call_args
	assert args[1] == user_id

import uuid
from datetime import date

import pytest
from app.repository import user_repository
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def test_create_and_get_by_id(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "alice", "alice@example.com", "hash")

	user = await user_repository.get_by_id(db_session, user_id)

	assert user is not None
	assert user.username == "alice"
	assert user.email == "alice@example.com"
	assert user.role == "member"
	assert user.is_active is True


async def test_get_by_id_not_found_returns_none(db_session: AsyncSession) -> None:
	user = await user_repository.get_by_id(db_session, uuid.uuid4())

	assert user is None


async def test_create_duplicate_username_raises_p0001(db_session: AsyncSession) -> None:
	await user_repository.create(db_session, "dupuser", "dup1@example.com", "hash")

	with pytest.raises(DBAPIError) as exc_info:
		await user_repository.create(db_session, "DupUser", "dup2@example.com", "hash")
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0001"


async def test_create_duplicate_email_raises_p0002(db_session: AsyncSession) -> None:
	await user_repository.create(db_session, "user1", "dup@example.com", "hash")

	with pytest.raises(DBAPIError) as exc_info:
		await user_repository.create(db_session, "user2", "Dup@example.com", "hash")
	assert getattr(exc_info.value.orig, "sqlstate", None) == "P0002"


async def test_get_by_login_identifier_by_username_and_email(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "bob", "bob@example.com", "hash")

	by_username = await user_repository.get_by_login_identifier(db_session, "bob")
	by_email = await user_repository.get_by_login_identifier(db_session, "bob@example.com")

	assert by_username is not None
	assert by_username.id == user_id
	assert by_email is not None
	assert by_email.id == user_id


async def test_get_by_email_not_found_returns_none(db_session: AsyncSession) -> None:
	user = await user_repository.get_by_email(db_session, "nobody@example.com")

	assert user is None


async def test_mark_email_verified_sets_timestamp(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "carol", "carol@example.com", "hash")

	await user_repository.mark_email_verified(db_session, user_id)

	user = await user_repository.get_by_id(db_session, user_id)
	assert user is not None
	assert user.email_verified_at is not None


async def test_update_password_changes_hash(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "dave", "dave@example.com", "old-hash")

	await user_repository.update_password(db_session, user_id, "new-hash")

	user = await user_repository.get_by_id(db_session, user_id)
	assert user is not None
	assert user.password_hash == "new-hash"


async def test_update_profile_sets_all_fields(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "erin", "erin@example.com", "hash")

	await user_repository.update_profile(
		db_session,
		user_id,
		last_name="山田",
		first_name="太郎",
		last_name_kana="ヤマダ",
		first_name_kana="タロウ",
		birth_date=date(1990, 1, 1),
	)

	user = await user_repository.get_by_id(db_session, user_id)
	assert user is not None
	assert user.last_name == "山田"
	assert user.first_name == "太郎"
	assert user.last_name_kana == "ヤマダ"
	assert user.first_name_kana == "タロウ"
	assert user.birth_date == date(1990, 1, 1)

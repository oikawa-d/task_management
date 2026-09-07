from app.repository import oauth_account_repository, user_repository
from sqlalchemy.ext.asyncio import AsyncSession


async def test_upsert_creates_link_and_verifies_email(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "alice", "alice@example.com", None)

	await oauth_account_repository.upsert(db_session, user_id, "google", "google-sub-1")

	user = await user_repository.get_by_id(db_session, user_id)
	assert user is not None
	assert user.email_verified_at is not None

	link = await oauth_account_repository.get_by_provider_identity(db_session, "google", "google-sub-1")
	assert link is not None
	assert link.user_id == user_id


async def test_upsert_does_not_overwrite_existing_verified_at(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "bob", "bob@example.com", "hash")
	await user_repository.mark_email_verified(db_session, user_id)
	user_before = await user_repository.get_by_id(db_session, user_id)
	assert user_before is not None

	await oauth_account_repository.upsert(db_session, user_id, "google", "google-sub-2")

	user_after = await user_repository.get_by_id(db_session, user_id)
	assert user_after is not None
	assert user_after.email_verified_at == user_before.email_verified_at


async def test_get_by_provider_identity_not_found_returns_none(db_session: AsyncSession) -> None:
	link = await oauth_account_repository.get_by_provider_identity(db_session, "google", "unknown-sub")

	assert link is None


async def test_list_by_user_id_returns_linked_accounts(db_session: AsyncSession) -> None:
	user_id = await user_repository.create(db_session, "carol", "carol@example.com", "hash")
	await oauth_account_repository.upsert(db_session, user_id, "google", "google-sub-3")

	links = await oauth_account_repository.list_by_user_id(db_session, user_id)

	assert len(links) == 1
	assert links[0].provider == "google"
	assert links[0].provider_user_id == "google-sub-3"

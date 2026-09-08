import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_account import OAuthAccount


async def get_by_provider_identity(db: AsyncSession, provider: str, provider_user_id: str) -> OAuthAccount | None:
	result = await db.execute(
		select(OAuthAccount)
		.from_statement(text("SELECT * FROM fn_find_oauth_account(:provider, :provider_user_id)"))
		.params(provider=provider, provider_user_id=provider_user_id)
	)
	return result.scalars().one_or_none()


async def list_by_user_id(db: AsyncSession, user_id: uuid.UUID) -> list[OAuthAccount]:
	result = await db.execute(
		select(OAuthAccount)
		.from_statement(text("SELECT * FROM fn_list_user_oauth_accounts(:user_id)"))
		.params(user_id=user_id)
	)
	return list(result.scalars().all())


async def upsert(
	db: AsyncSession,
	user_id: uuid.UUID,
	provider: str,
	provider_user_id: str,
	provider_email: str | None = None,
) -> None:
	await db.execute(
		text("CALL sp_upsert_oauth_account(:user_id, :provider, :provider_user_id)"),
		{"user_id": user_id, "provider": provider, "provider_user_id": provider_user_id},
	)
	if provider_email is not None:
		await db.execute(
			text(
				"UPDATE oauth_accounts SET provider_email = :provider_email "
				"WHERE user_id = :user_id AND provider = :provider AND provider_user_id = :provider_user_id"
			),
			{
				"provider_email": provider_email,
				"user_id": user_id,
				"provider": provider,
				"provider_user_id": provider_user_id,
			},
		)

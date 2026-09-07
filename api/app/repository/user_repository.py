import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
	result = await db.execute(
		select(User).from_statement(text("SELECT * FROM fn_get_user(:user_id)")).params(user_id=user_id)
	)
	return result.scalars().one_or_none()


async def get_by_login_identifier(db: AsyncSession, identifier: str) -> User | None:
	result = await db.execute(
		select(User)
		.from_statement(text("SELECT * FROM fn_find_user_by_identifier(:identifier)"))
		.params(identifier=identifier)
	)
	return result.scalars().one_or_none()


async def get_by_email(db: AsyncSession, email: str) -> User | None:
	result = await db.execute(
		select(User).from_statement(text("SELECT * FROM fn_find_user_by_email(:email)")).params(email=email)
	)
	return result.scalars().one_or_none()


async def create(db: AsyncSession, username: str, email: str, password_hash: str | None) -> uuid.UUID:
	result = await db.execute(
		text("CALL sp_register_user(:username, :email, :password_hash, NULL)"),
		{"username": username, "email": email, "password_hash": password_hash},
	)
	user_id: uuid.UUID = result.mappings().one()["p_user_id"]
	return user_id


async def mark_email_verified(db: AsyncSession, user_id: uuid.UUID) -> None:
	await db.execute(text("CALL sp_verify_user_email(:user_id)"), {"user_id": user_id})


async def update_password(db: AsyncSession, user_id: uuid.UUID, password_hash: str) -> None:
	await db.execute(
		text("CALL sp_update_user_password(:user_id, :password_hash)"),
		{"user_id": user_id, "password_hash": password_hash},
	)


async def update_profile(
	db: AsyncSession,
	user_id: uuid.UUID,
	last_name: str | None,
	first_name: str | None,
	last_name_kana: str | None,
	first_name_kana: str | None,
	birth_date: date | None,
) -> None:
	await db.execute(
		text(
			"CALL sp_update_user_profile("
			":user_id, :last_name, :first_name, :last_name_kana, :first_name_kana, :birth_date)"
		),
		{
			"user_id": user_id,
			"last_name": last_name,
			"first_name": first_name,
			"last_name_kana": last_name_kana,
			"first_name_kana": first_name_kana,
			"birth_date": birth_date,
		},
	)

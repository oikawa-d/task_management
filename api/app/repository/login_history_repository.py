import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_history import LoginHistory


async def create(
	db: AsyncSession,
	user_id: uuid.UUID | None,
	login_identifier: str,
	login_method: str,
	ip_address: str | None,
	user_agent: str | None,
	success: bool,
	failure_reason: str | None,
) -> None:
	await db.execute(
		text(
			"CALL sp_record_login_history("
			":user_id, :login_identifier, :login_method, :ip_address, :user_agent, :success, :failure_reason)"
		),
		{
			"user_id": user_id,
			"login_identifier": login_identifier,
			"login_method": login_method,
			"ip_address": ip_address,
			"user_agent": user_agent,
			"success": success,
			"failure_reason": failure_reason,
		},
	)


async def list_by_user_id(db: AsyncSession, user_id: uuid.UUID, limit: int = 50, offset: int = 0) -> list[LoginHistory]:
	result = await db.execute(
		select(LoginHistory)
		.from_statement(text("SELECT * FROM fn_list_user_login_history(:user_id, :limit, :offset)"))
		.params(user_id=user_id, limit=limit, offset=offset)
	)
	return list(result.scalars().all())


async def purge_expired(db: AsyncSession, retention_days: int) -> None:
	await db.execute(text("CALL sp_purge_login_history(:retention_days)"), {"retention_days": retention_days})

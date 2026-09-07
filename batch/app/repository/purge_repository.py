from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def purge_notifications(db: AsyncSession, retention_days: int) -> None:
	await db.execute(
		text("CALL sp_purge_notifications(:retention_days)"),
		{"retention_days": retention_days},
	)

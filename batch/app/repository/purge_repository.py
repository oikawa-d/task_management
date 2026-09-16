from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def purge_notifications(db: AsyncSession, retention_days: int) -> None:
	await db.execute(
		text("CALL sp_purge_notifications(:retention_days)"),
		{"retention_days": retention_days},
	)


async def purge_api_history(db: AsyncSession, retention_days: int) -> None:
	await db.execute(text("CALL sp_purge_api_history(:retention_days)"), {"retention_days": retention_days})


async def purge_batch_history(db: AsyncSession, retention_days: int) -> None:
	await db.execute(text("CALL sp_purge_batch_history(:retention_days)"), {"retention_days": retention_days})

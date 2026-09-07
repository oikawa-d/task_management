from sqlalchemy.ext.asyncio import AsyncSession

from app.repository import purge_repository


async def purge_notifications(db: AsyncSession, retention_days: int) -> None:
	try:
		await purge_repository.purge_notifications(db, retention_days=retention_days)
		await db.commit()
	except Exception:
		await db.rollback()
		raise

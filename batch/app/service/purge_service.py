from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BatchSettings
from app.repository import purge_repository


async def purge_notifications(db: AsyncSession, retention_days: int) -> None:
	try:
		await purge_repository.purge_notifications(db, retention_days=retention_days)
		await db.commit()
	except Exception:
		await db.rollback()
		raise


async def purge_histories(db: AsyncSession, settings: BatchSettings) -> None:
	try:
		await purge_repository.purge_notifications(db, settings.notification_retention_days)
		await purge_repository.purge_api_history(db, settings.api_history_retention_days)
		await purge_repository.purge_batch_history(db, settings.batch_history_retention_days)
		await db.commit()
	except Exception:
		await db.rollback()
		raise

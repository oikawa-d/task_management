"""通知・api_history・batch_historyの保持期間パージをトランザクション付きで実行するservice。

ジョブ本体のトランザクションとは分離し、パージ失敗時は通知作成済みデータを維持したまま
ジョブを失敗扱いにできるようにする（02_due_notification_job.md §6・§11）。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BatchSettings
from app.repository import purge_repository


async def purge_notifications(db: AsyncSession, retention_days: int) -> None:
	"""`notifications`の保持期間パージを実行してコミットし、失敗時はロールバックして再送出する。

	Args:
		db: 呼び出し元が管理するAsyncSession。
		retention_days: 保持日数（`NOTIFICATION_RETENTION_DAYS`）。

	Raises:
		Exception: repository呼び出しで発生した例外をロールバック後に再送出する。
	"""
	try:
		await purge_repository.purge_notifications(db, retention_days=retention_days)
		await db.commit()
	except Exception:
		await db.rollback()
		raise


async def purge_histories(db: AsyncSession, settings: BatchSettings) -> None:
	"""通知・api_history・batch_historyの3種の保持期間パージを1トランザクションで順に実行する。

	`login_history`は本関数の対象外とし、運用者が手動で実行する方針とする
	（00_overview.md §7.1）。

	Args:
		db: 呼び出し元が管理するAsyncSession。
		settings: 各保持日数（`notification_retention_days`等）を含むBatchSettings。

	Raises:
		Exception: いずれかのパージで発生した例外をロールバック後に再送出する。
	"""
	try:
		await purge_repository.purge_notifications(db, settings.notification_retention_days)
		await purge_repository.purge_api_history(db, settings.api_history_retention_days)
		await purge_repository.purge_batch_history(db, settings.batch_history_retention_days)
		await db.commit()
	except Exception:
		await db.rollback()
		raise

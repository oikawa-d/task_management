"""通知・api_history・batch_historyの保持期間パージを行うストアドプロシージャ呼び出しrepository。

日次ジョブ末尾で各保持期間設定値を渡して実行する（02_due_notification_job.md §1・§7）。
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def purge_notifications(db: AsyncSession, retention_days: int) -> None:
	"""保持期間を超えた`notifications`行をストアドプロシージャ`sp_purge_notifications`でパージする。

	Args:
		db: 呼び出し元が管理するAsyncSession。コミットは呼び出し元の責務。
		retention_days: 保持日数（`NOTIFICATION_RETENTION_DAYS`）。

	Raises:
		sqlalchemy.exc.SQLAlchemyError: プロシージャ呼び出し失敗時。
	"""
	await db.execute(
		text("CALL sp_purge_notifications(:retention_days)"),
		{"retention_days": retention_days},
	)


async def purge_api_history(db: AsyncSession, retention_days: int) -> None:
	"""保持期間を超えた`api_history`行をストアドプロシージャ`sp_purge_api_history`でパージする。

	Args:
		db: 呼び出し元が管理するAsyncSession。コミットは呼び出し元の責務。
		retention_days: `created_at`基準の保持日数（`API_HISTORY_RETENTION_DAYS`）。

	Raises:
		sqlalchemy.exc.SQLAlchemyError: プロシージャ呼び出し失敗時。
	"""
	await db.execute(text("CALL sp_purge_api_history(:retention_days)"), {"retention_days": retention_days})


async def purge_batch_history(db: AsyncSession, retention_days: int) -> None:
	"""保持期間を超えた`batch_history`行をストアドプロシージャ`sp_purge_batch_history`でパージする。

	Args:
		db: 呼び出し元が管理するAsyncSession。コミットは呼び出し元の責務。
		retention_days: `started_at`基準の保持日数（`BATCH_HISTORY_RETENTION_DAYS`）。

	Raises:
		sqlalchemy.exc.SQLAlchemyError: プロシージャ呼び出し失敗時。
	"""
	await db.execute(text("CALL sp_purge_batch_history(:retention_days)"), {"retention_days": retention_days})

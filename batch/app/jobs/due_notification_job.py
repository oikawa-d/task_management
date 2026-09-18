"""毎日10時・17時に実行する期限通知ジョブ本体。

APSchedulerから起動され、Redis実行ロックで多重実行を防ぎつつ期限が近いタスクを抽出して
通知を作成し、末尾で通知・api_history・batch_historyの保持期間パージを行う。冪等性は
Redisの日付・実行枠別ロックと`notifications`の`UNIQUE (user_id, dedupe_key)`制約による
二重防御で担保する（詳細設計: docs/detailed_design/batch/02_due_notification_job.md）。
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import cast
from zoneinfo import ZoneInfo

from app.core.config import BatchSettings
from app.db import get_session_factory
from app.redis_client import get_redis_client
from app.repository import batch_history_repository, redis_lock, task_repository
from app.service import notification_service, purge_service

logger = logging.getLogger("app.jobs.due_notification_job")


@dataclass(frozen=True, slots=True)
class JobResult:
	"""1回のジョブ実行結果を表す。`batch_history`への記録とログ出力に使う。"""

	target_count: int
	success_count: int
	skipped_count: int
	lock_acquired: bool


def _run_date_and_threshold(now: datetime, settings: BatchSettings) -> tuple[date, datetime]:
	"""実行日（ローカル日付）と抽出閾値（翌日`NOTIFY_DUE_TARGET_HOUR`のUTC日時）を算出する。

	10時枠・17時枠のいずれも同じ閾値（翌日10時ちょうどを含む）を共有する
	（02_due_notification_job.md §1）。

	Args:
		now: 実行時刻（タイムゾーン付きdatetime）。
		settings: `app_timezone`・`notify_due_target_hour`を含むBatchSettings。

	Returns:
		`(実行日のローカル日付, 抽出閾値のUTC日時)`のタプル。
	"""
	local_now = now.astimezone(ZoneInfo(settings.app_timezone))
	run_date = local_now.date()
	next_day = run_date + timedelta(days=1)
	local_threshold = datetime.combine(
		next_day,
		time(hour=settings.notify_due_target_hour, tzinfo=ZoneInfo(settings.app_timezone)),
	)
	return run_date, local_threshold.astimezone(timezone.utc)


async def run_due_notification_job(*, now: datetime, settings: BatchSettings, notification_slot: str) -> JobResult:
	"""期限通知ジョブ本体。抽出・通知作成・保持期間パージ・履歴記録を1回分実行する。

	`batch_history`へ`inprogress`を記録した後、実行枠別のRedisロックを`SET NX EX`で取得する。
	取得できない場合は別プロセスが実行済み/実行中とみなし、何もせず`skipped_count=1`で
	`complete`にする。取得できた場合はチャンク単位で対象タスクを抽出し、`ON CONFLICT DO
	NOTHING`で通知を作成した後、通知・api_history・batch_historyの保持期間パージを実行する。
	成功時はロックをTTLまで保持して同一実行枠の再実行を抑止し、失敗時は`runner_id`が自分の
	ものであることを確認したうえでロックを解放して再実行可能にする（02_due_notification_job.md
	§5・§6）。

	Args:
		now: ジョブ起動時刻。
		settings: `BatchSettings`。閾値算出・チャンクサイズ・ロックTTL・保持日数を含む。
		notification_slot: 実行枠（例: `10`/`17`）。ロックキーと`dedupe_key`に使う。

	Returns:
		処理件数・スキップ件数・ロック取得可否を含む`JobResult`。ジョブ本体・パージが失敗した
		場合は全件0のJobResultを返す（例外は送出せず、失敗は`batch_history`とログに記録する）。
	"""
	run_date, threshold_utc = _run_date_and_threshold(now, settings)
	runner_id = str(uuid.uuid4())
	redis = get_redis_client(settings)
	lock_acquired = False
	job_failed = False
	run_id: uuid.UUID | None = None
	db = None
	try:
		async with get_session_factory()() as db:
			run_id = await batch_history_repository.start(db, "due_notification", "scheduled", notification_slot)
			await db.commit()
			lock_client = cast(redis_lock.RedisLockClient, redis)
			lock_acquired = await redis_lock.acquire_due_notification_lock(
				lock_client,
				run_date,
				notification_slot,
				runner_id,
				settings.notify_due_lock_ttl_seconds,
				settings.redis_key_prefix,
			)
			if not lock_acquired:
				await batch_history_repository.complete(db, run_id, 0, 0, 1)
				await db.commit()
				return JobResult(0, 0, 1, False)

			due_tasks = [
				task
				async for task in task_repository.iter_due_tasks(
					db, threshold_utc, settings.notify_due_batch_chunk_size
				)
			]
			tasks = [
				notification_service.DueTask(task.id, task.title, task.assignee_id, task.due_at) for task in due_tasks
			]
			created_count = await notification_service.bulk_create_due_notifications(
				db,
				tasks,
				run_date,
				notification_slot,
				settings.notify_due_batch_chunk_size,
			)
			await purge_service.purge_histories(db, settings)
			await batch_history_repository.complete(db, run_id, len(tasks), created_count, 0)
			await db.commit()
			return JobResult(len(tasks), created_count, 0, True)
	except Exception as exc:
		job_failed = True
		if run_id is not None:
			if db is not None:
				try:
					await db.rollback()
				except Exception:
					logger.exception("failed to rollback due notification transaction")
			try:
				async with get_session_factory()() as history_db:
					await batch_history_repository.fail(
						history_db, run_id, "DUE_NOTIFICATION_FAILED", str(exc), 0, 0, 0
					)
					await history_db.commit()
			except Exception:
				logger.exception("failed to update batch history", extra={"run_id": str(run_id)})
		logger.exception("due notification job failed", extra={"run_id": str(run_id) if run_id else None})
		return JobResult(0, 0, 0, lock_acquired)
	finally:
		if lock_acquired and job_failed:
			try:
				await redis_lock.release_due_notification_lock(
					cast(redis_lock.RedisLockClient, redis),
					run_date,
					notification_slot,
					runner_id,
					settings.redis_key_prefix,
				)
			except Exception:
				logger.exception("failed to release due notification lock")

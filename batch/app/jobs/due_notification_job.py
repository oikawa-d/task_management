import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import cast
from zoneinfo import ZoneInfo

from app.core.config import BatchSettings
from app.db import get_session_factory
from app.redis_client import create_redis_client
from app.repository import batch_history_repository, redis_lock, task_repository
from app.service import notification_service, purge_service

logger = logging.getLogger("app.jobs.due_notification_job")


@dataclass(frozen=True, slots=True)
class JobResult:
	target_count: int
	success_count: int
	skipped_count: int
	lock_acquired: bool


def _run_date_and_threshold(now: datetime, settings: BatchSettings) -> tuple[date, datetime]:
	local_now = now.astimezone(ZoneInfo(settings.app_timezone))
	run_date = local_now.date()
	next_day = run_date + timedelta(days=1)
	local_threshold = datetime.combine(
		next_day,
		time(hour=settings.notify_due_target_hour, tzinfo=ZoneInfo(settings.app_timezone)),
	)
	return run_date, local_threshold.astimezone(timezone.utc)


async def run_due_notification_job(*, now: datetime, settings: BatchSettings, notification_slot: str) -> JobResult:
	run_date, threshold_utc = _run_date_and_threshold(now, settings)
	runner_id = str(uuid.uuid4())
	redis = create_redis_client(settings)
	lock_acquired = False
	job_failed = False
	run_id: uuid.UUID | None = None
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
			try:
				await batch_history_repository.fail(db, run_id, "DUE_NOTIFICATION_FAILED", str(exc), 0, 0, 0)
				await db.commit()
			except Exception:
				logger.exception("failed to update batch history", extra={"run_id": str(run_id)})
		logger.exception("due notification job failed", extra={"run_id": str(run_id) if run_id else None})
		return JobResult(0, 0, 0, lock_acquired)
	finally:
		if lock_acquired and job_failed:
			try:
				await redis_lock.release_due_notification_lock(
					cast(redis_lock.RedisLockClient, redis), run_date, notification_slot, runner_id
				)
			except Exception:
				logger.exception("failed to release due notification lock")
		await redis.aclose()

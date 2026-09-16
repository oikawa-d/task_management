import argparse
import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from importlib import import_module
from types import FrameType
from typing import Any, cast
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from app.core.config import BatchSettings, get_batch_settings
from app.core.logger import configure_logging
from app.db import dispose_db_engine, get_db_engine
from app.redis_client import close_redis_client, get_redis_client

logger = logging.getLogger("app.main")
JobRunner = Callable[..., Awaitable[Any]]


def _parse_hour(value: str) -> int:
	try:
		hour = int(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError("時刻は整数で指定してください") from exc
	if not 0 <= hour <= 23:
		raise argparse.ArgumentTypeError("時刻は0から23の範囲で指定してください")
	return hour


def _parse_run_hours(value: str) -> list[int]:
	hours: list[int] = []
	for raw_hour in value.split(","):
		if not raw_hour.strip():
			raise ValueError("NOTIFY_DUE_RUN_HOURSに空の時刻は指定できません")
		hour = int(raw_hour.strip())
		if not 0 <= hour <= 23:
			raise ValueError("NOTIFY_DUE_RUN_HOURSは0から23の範囲で指定してください")
		if hour in hours:
			raise ValueError("NOTIFY_DUE_RUN_HOURSに同じ時刻を重複指定できません")
		hours.append(hour)
	return hours


async def run_due_notification_job(*, slot: int, settings: BatchSettings | None = None) -> Any:
	"""期限通知ジョブを遅延importして実行するスケジューラ境界。"""
	settings = settings or get_batch_settings()
	module = import_module("app.jobs.due_notification_job")
	job = cast(JobRunner, getattr(module, "run_due_notification_job"))
	now = datetime.now(ZoneInfo(settings.app_timezone))
	return await job(now=now, settings=settings, notification_slot=str(slot))


def build_scheduler(settings: BatchSettings) -> AsyncIOScheduler:
	timezone = ZoneInfo(settings.app_timezone)
	scheduler = AsyncIOScheduler(timezone=timezone)
	if not settings.batch_enabled:
		return scheduler

	for hour in _parse_run_hours(settings.notify_due_run_hours):
		scheduler.add_job(
			run_due_notification_job,
			trigger=CronTrigger(
				hour=hour,
				minute=settings.notify_due_cron_minute,
				timezone=timezone,
			),
			id=f"due_notification_{hour}",
			kwargs={"slot": hour},
			coalesce=True,
			max_instances=1,
		)
	return scheduler


def handle_sigterm(_scheduler: AsyncIOScheduler, shutdown_event: asyncio.Event) -> None:
	shutdown_event.set()


async def async_main(args: argparse.Namespace, settings: BatchSettings | None = None) -> None:
	settings = settings or get_batch_settings()
	needs_resources = bool(args.run_once or settings.batch_enabled)
	db_initialized = False
	redis_initialized = False
	scheduler: AsyncIOScheduler | None = None
	try:
		if needs_resources:
			get_db_engine()
			db_initialized = True
			get_redis_client(settings)
			redis_initialized = True

		shutdown_event = asyncio.Event()
		scheduler = build_scheduler(settings) if not args.run_once else None

		def on_signal(signum: int, frame: FrameType | None) -> None:
			if scheduler is not None:
				handle_sigterm(scheduler, shutdown_event)

		signal.signal(signal.SIGTERM, on_signal)
		signal.signal(signal.SIGINT, on_signal)
		if args.run_once:
			if args.slot is None:
				raise ValueError("--run-onceには--slotが必要です")
			await run_due_notification_job(slot=args.slot, settings=settings)
			return
		if settings.batch_enabled and scheduler is not None:
			scheduler.start()
			logger.info("batch scheduler started")
		else:
			logger.info("BATCH_ENABLED=false; scheduled jobs are disabled")
		await shutdown_event.wait()
	finally:
		if scheduler is not None and scheduler.running:
			scheduler.shutdown(wait=True)
		if redis_initialized:
			await close_redis_client()
		if db_initialized:
			await dispose_db_engine()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="常駐batchスケジューラ")
	parser.add_argument("--run-once", choices=("due_notification",))
	parser.add_argument("--slot", type=_parse_hour)
	args = parser.parse_args(argv)
	if args.run_once and args.slot is None:
		parser.error("--run-onceには--slotが必要です")
	if args.slot is not None and not args.run_once:
		parser.error("--slotは--run-onceと同時に指定してください")
	return args


def main(argv: Sequence[str] | None = None) -> None:
	args = _parse_args(argv)
	settings = get_batch_settings()
	configure_logging(settings.log_level)
	logger.info("batch process starting")
	asyncio.run(async_main(args, settings))


if __name__ == "__main__":
	main()

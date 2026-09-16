import asyncio
import signal
from argparse import Namespace
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from app import main
from app.core.config import BatchSettings
from apscheduler.triggers.cron import CronTrigger


def _settings(*, enabled: bool = True, hours: str = "10,17") -> BatchSettings:
	return BatchSettings(
		_env_file=None,
		database_url="postgresql+asyncpg://user:password@localhost:5432/test",
		app_timezone="Asia/Tokyo",
		notify_due_run_hours=hours,
		notify_due_cron_minute=15,
		batch_enabled=enabled,
	)


def test_build_scheduler_registers_jobs_at_configured_times() -> None:
	settings = _settings()

	scheduler = main.build_scheduler(settings)
	jobs = {job.id: job for job in scheduler.get_jobs()}

	assert set(jobs) == {"due_notification_10", "due_notification_17"}
	for hour in (10, 17):
		job = jobs[f"due_notification_{hour}"]
		assert job.func == main.run_due_notification_job
		assert job.kwargs == {"slot": hour}
		assert job.coalesce is True
		assert job.max_instances == 1
		assert isinstance(job.trigger, CronTrigger)
		assert job.trigger.timezone == ZoneInfo("Asia/Tokyo")
		fire_time = job.trigger.get_next_fire_time(
			None,
			datetime(2026, 9, 7, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
		)
		assert fire_time is not None
		assert (fire_time.hour, fire_time.minute) == (hour, 15)


def test_build_scheduler_skips_jobs_when_disabled() -> None:
	scheduler = main.build_scheduler(_settings(enabled=False))

	assert scheduler.get_jobs() == []


def test_build_scheduler_parses_configured_run_hours() -> None:
	scheduler = main.build_scheduler(_settings(hours="6, 18"))

	assert [job.id for job in scheduler.get_jobs()] == ["due_notification_6", "due_notification_18"]


def test_build_scheduler_rejects_invalid_run_hour() -> None:
	with pytest.raises(ValueError, match="0から23の範囲"):
		main.build_scheduler(_settings(hours="10,24"))


def test_async_main_run_once_executes_job_without_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
	job = AsyncMock()
	build_scheduler = MagicMock()
	get_engine = MagicMock()
	get_redis = MagicMock()
	close_redis = AsyncMock()
	dispose_engine = AsyncMock()
	monkeypatch.setattr(main, "run_due_notification_job", job)
	monkeypatch.setattr(main, "build_scheduler", build_scheduler)
	monkeypatch.setattr(main, "get_db_engine", get_engine)
	monkeypatch.setattr(main, "get_redis_client", get_redis)
	monkeypatch.setattr(main, "close_redis_client", close_redis)
	monkeypatch.setattr(main, "dispose_db_engine", dispose_engine)
	settings = _settings(enabled=False)
	args = Namespace(run_once="due_notification", slot=17)

	asyncio.run(main.async_main(args, settings))

	job.assert_awaited_once_with(slot=17, settings=settings)
	build_scheduler.assert_not_called()
	get_engine.assert_called_once_with()
	get_redis.assert_called_once_with(settings)
	close_redis.assert_awaited_once_with()
	dispose_engine.assert_awaited_once_with()


def test_handle_sigterm_sets_shutdown_event() -> None:
	event = asyncio.Event()

	main.handle_sigterm(MagicMock(), event)

	assert event.is_set()


def test_async_main_shuts_down_scheduler_after_signal(monkeypatch: pytest.MonkeyPatch) -> None:
	scheduler = MagicMock()
	scheduler.running = True
	handlers: dict[int, object] = {}

	def register_handler(signum: int, handler: object) -> object:
		handlers[signum] = handler
		return signal.SIG_DFL

	def start_scheduler() -> None:
		handler = handlers[signal.SIGTERM]
		assert callable(handler)
		handler(signal.SIGTERM, None)

	scheduler.start.side_effect = start_scheduler
	monkeypatch.setattr(main, "build_scheduler", lambda settings: scheduler)
	monkeypatch.setattr(main.signal, "signal", register_handler)

	asyncio.run(main.async_main(Namespace(run_once=None, slot=None), _settings()))

	scheduler.start.assert_called_once_with()
	scheduler.shutdown.assert_called_once_with(wait=True)


def test_async_main_disabled_does_not_create_datastore_resources(monkeypatch: pytest.MonkeyPatch) -> None:
	scheduler = MagicMock()
	monkeypatch.setattr(main, "build_scheduler", lambda settings: scheduler)
	get_engine = MagicMock()
	get_redis = MagicMock()
	close_redis = AsyncMock()
	dispose_engine = AsyncMock()
	monkeypatch.setattr(main, "get_db_engine", get_engine)
	monkeypatch.setattr(main, "get_redis_client", get_redis)
	monkeypatch.setattr(main, "close_redis_client", close_redis)
	monkeypatch.setattr(main, "dispose_db_engine", dispose_engine)

	def stop_on_signal(_signum: int, handler: object) -> object:
		assert callable(handler)
		handler(signal.SIGTERM, None)
		return signal.SIG_DFL

	monkeypatch.setattr(main.signal, "signal", stop_on_signal)
	asyncio.run(main.async_main(Namespace(run_once=None, slot=None), _settings(enabled=False)))

	get_engine.assert_not_called()
	get_redis.assert_not_called()
	close_redis.assert_not_awaited()
	dispose_engine.assert_not_awaited()


def test_async_main_disposes_db_when_redis_initialization_fails(monkeypatch: pytest.MonkeyPatch) -> None:
	get_engine = MagicMock()
	monkeypatch.setattr(main, "get_db_engine", get_engine)
	monkeypatch.setattr(main, "get_redis_client", MagicMock(side_effect=RuntimeError("redis unavailable")))
	close_redis = AsyncMock()
	dispose_engine = AsyncMock()
	monkeypatch.setattr(main, "close_redis_client", close_redis)
	monkeypatch.setattr(main, "dispose_db_engine", dispose_engine)

	with pytest.raises(RuntimeError, match="redis unavailable"):
		asyncio.run(main.async_main(Namespace(run_once="due_notification", slot=10), _settings()))

	get_engine.assert_called_once_with()
	close_redis.assert_not_awaited()
	dispose_engine.assert_awaited_once_with()

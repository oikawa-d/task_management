from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.core.config import BatchSettings
from app.jobs import due_notification_job
from app.repository.task_repository import DueTask


def _settings() -> BatchSettings:
	return BatchSettings(
		_env_file=None,
		database_url="postgresql+asyncpg://user:password@localhost:5432/test",
		redis_url="redis://localhost:6379/1",
	)


@pytest.mark.asyncio
async def test_due_job_uses_next_day_target_and_completes(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = _settings()
	db = MagicMock()
	db.commit = AsyncMock()
	db.rollback = AsyncMock()
	session = MagicMock()
	session.__aenter__ = AsyncMock(return_value=db)
	session.__aexit__ = AsyncMock(return_value=None)
	factory = MagicMock(return_value=session)
	redis = MagicMock()
	redis.aclose = AsyncMock()
	task = DueTask(MagicMock(), None, "期限タスク", MagicMock(), datetime.now(timezone.utc))

	monkeypatch.setattr(due_notification_job, "get_session_factory", lambda: factory)
	monkeypatch.setattr(due_notification_job, "get_redis_client", lambda _: redis)
	monkeypatch.setattr(due_notification_job.batch_history_repository, "start", AsyncMock(return_value=MagicMock()))
	monkeypatch.setattr(due_notification_job.batch_history_repository, "complete", AsyncMock())
	monkeypatch.setattr(
		due_notification_job.redis_lock,
		"acquire_due_notification_lock",
		AsyncMock(return_value=True),
	)
	monkeypatch.setattr(due_notification_job.redis_lock, "release_due_notification_lock", AsyncMock())
	monkeypatch.setattr(
		due_notification_job.task_repository,
		"iter_due_tasks",
		lambda *_args: _tasks(task),
	)
	monkeypatch.setattr(
		due_notification_job.notification_service,
		"bulk_create_due_notifications",
		AsyncMock(return_value=1),
	)
	monkeypatch.setattr(due_notification_job.purge_service, "purge_histories", AsyncMock())

	result = await due_notification_job.run_due_notification_job(
		now=datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc), settings=settings, notification_slot="10"
	)

	assert result == due_notification_job.JobResult(1, 1, 0, True)
	due_notification_job.purge_service.purge_histories.assert_awaited_once_with(db, settings)
	due_notification_job.redis_lock.release_due_notification_lock.assert_not_awaited()


@pytest.mark.asyncio
async def test_due_job_skips_when_slot_lock_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
	settings = _settings()
	db = MagicMock()
	db.commit = AsyncMock()
	session = MagicMock()
	session.__aenter__ = AsyncMock(return_value=db)
	session.__aexit__ = AsyncMock(return_value=None)
	redis = MagicMock()
	redis.aclose = AsyncMock()
	monkeypatch.setattr(due_notification_job, "get_session_factory", lambda: MagicMock(return_value=session))
	monkeypatch.setattr(due_notification_job, "get_redis_client", lambda _: redis)
	monkeypatch.setattr(due_notification_job.batch_history_repository, "start", AsyncMock(return_value=MagicMock()))
	complete = AsyncMock()
	monkeypatch.setattr(due_notification_job.batch_history_repository, "complete", complete)
	monkeypatch.setattr(due_notification_job.redis_lock, "acquire_due_notification_lock", AsyncMock(return_value=False))

	result = await due_notification_job.run_due_notification_job(
		now=datetime(2026, 9, 7, tzinfo=timezone.utc), settings=settings, notification_slot="17"
	)

	assert result == due_notification_job.JobResult(0, 0, 1, False)
	complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_due_job_rolls_back_failed_work_and_records_failure_in_separate_session(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	settings = _settings()
	work_db = MagicMock()
	work_db.commit = AsyncMock()
	work_db.rollback = AsyncMock()
	history_db = MagicMock()
	history_db.commit = AsyncMock()
	work_session = MagicMock()
	work_session.__aenter__ = AsyncMock(return_value=work_db)
	work_session.__aexit__ = AsyncMock(return_value=None)
	history_session = MagicMock()
	history_session.__aenter__ = AsyncMock(return_value=history_db)
	history_session.__aexit__ = AsyncMock(return_value=None)
	factory = MagicMock(side_effect=[work_session, history_session])
	run_id = uuid4()
	redis = MagicMock()
	task = DueTask(uuid4(), None, "期限タスク", uuid4(), datetime.now(timezone.utc))

	monkeypatch.setattr(due_notification_job, "get_session_factory", lambda: factory)
	monkeypatch.setattr(due_notification_job, "get_redis_client", lambda _: redis)
	monkeypatch.setattr(due_notification_job.batch_history_repository, "start", AsyncMock(return_value=run_id))
	fail = AsyncMock()
	monkeypatch.setattr(due_notification_job.batch_history_repository, "fail", fail)
	monkeypatch.setattr(due_notification_job.redis_lock, "acquire_due_notification_lock", AsyncMock(return_value=True))
	release = AsyncMock()
	monkeypatch.setattr(due_notification_job.redis_lock, "release_due_notification_lock", release)
	monkeypatch.setattr(due_notification_job.task_repository, "iter_due_tasks", lambda *_args: _tasks(task))
	monkeypatch.setattr(
		due_notification_job.notification_service,
		"bulk_create_due_notifications",
		AsyncMock(side_effect=RuntimeError("notification insert failed")),
	)

	result = await due_notification_job.run_due_notification_job(
		now=datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc), settings=settings, notification_slot="10"
	)

	assert result == due_notification_job.JobResult(0, 0, 0, True)
	work_db.rollback.assert_awaited_once()
	fail.assert_awaited_once_with(history_db, run_id, "DUE_NOTIFICATION_FAILED", "notification insert failed", 0, 0, 0)
	history_db.commit.assert_awaited_once()
	release.assert_awaited_once()


@pytest.mark.asyncio
async def test_due_job_records_failure_even_when_work_transaction_rollback_fails(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	settings = _settings()
	work_db = MagicMock()
	work_db.commit = AsyncMock()
	work_db.rollback = AsyncMock(side_effect=RuntimeError("rollback failed"))
	history_db = MagicMock()
	history_db.commit = AsyncMock()
	work_session = MagicMock()
	work_session.__aenter__ = AsyncMock(return_value=work_db)
	work_session.__aexit__ = AsyncMock(return_value=None)
	history_session = MagicMock()
	history_session.__aenter__ = AsyncMock(return_value=history_db)
	history_session.__aexit__ = AsyncMock(return_value=None)
	factory = MagicMock(side_effect=[work_session, history_session])
	run_id = uuid4()
	redis = MagicMock()
	task = DueTask(uuid4(), None, "期限タスク", uuid4(), datetime.now(timezone.utc))

	monkeypatch.setattr(due_notification_job, "get_session_factory", lambda: factory)
	monkeypatch.setattr(due_notification_job, "get_redis_client", lambda _: redis)
	monkeypatch.setattr(due_notification_job.batch_history_repository, "start", AsyncMock(return_value=run_id))
	fail = AsyncMock()
	monkeypatch.setattr(due_notification_job.batch_history_repository, "fail", fail)
	monkeypatch.setattr(due_notification_job.redis_lock, "acquire_due_notification_lock", AsyncMock(return_value=True))
	monkeypatch.setattr(due_notification_job.redis_lock, "release_due_notification_lock", AsyncMock())
	monkeypatch.setattr(due_notification_job.task_repository, "iter_due_tasks", lambda *_args: _tasks(task))
	monkeypatch.setattr(
		due_notification_job.notification_service,
		"bulk_create_due_notifications",
		AsyncMock(side_effect=RuntimeError("notification insert failed")),
	)

	result = await due_notification_job.run_due_notification_job(
		now=datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc), settings=settings, notification_slot="10"
	)

	assert result.lock_acquired is True
	work_db.rollback.assert_awaited_once()
	fail.assert_awaited_once()
	history_db.commit.assert_awaited_once()


async def _tasks(task: DueTask):
	yield task

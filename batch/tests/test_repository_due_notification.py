import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Self

import pytest
from app.repository import redis_lock, task_repository


class _Result:
	def __init__(self, rows: list[dict[str, object]]) -> None:
		self._rows = rows

	def mappings(self) -> Self:
		return self

	def all(self) -> list[dict[str, object]]:
		return self._rows


class _Session:
	def __init__(self, batches: list[list[dict[str, object]]]) -> None:
		self.batches = batches
		self.calls: list[tuple[str, dict[str, object]]] = []

	async def execute(self, statement: object, params: dict[str, object]) -> _Result:
		self.calls.append((str(statement), params))
		return _Result(self.batches.pop(0))


class _Redis:
	def __init__(self) -> None:
		self.values: dict[str, str] = {}
		self.ttls: dict[str, int] = {}
		self._lock = asyncio.Lock()

	async def set(self, name: str, value: str, *, ex: int, nx: bool) -> bool:
		async with self._lock:
			if nx and name in self.values:
				return False
			self.values[name] = value
			self.ttls[name] = ex
			return True

	async def eval(self, script: str, numkeys: int, key: str, value: str) -> int:
		async with self._lock:
			if self.values.get(key) != value:
				return 0
			del self.values[key]
			return 1


def _task_row(task_id: uuid.UUID, due_at: datetime) -> dict[str, object]:
	return {
		"id": task_id,
		"project_id": uuid.uuid4(),
		"title": "期限タスク",
		"assignee_id": uuid.uuid4(),
		"due_at": due_at,
	}


async def test_iter_due_tasks_selects_unfinished_assigned_tasks_until_threshold() -> None:
	threshold = datetime(2026, 9, 8, 1, tzinfo=UTC)
	rows = [_task_row(uuid.uuid4(), threshold)]
	db = _Session([rows, []])

	result = [task async for task in task_repository.iter_due_tasks(db, threshold, chunk_size=10)]

	assert result[0].due_at == threshold
	assert len(result) == 1
	query, params = db.calls[0]
	assert "status <> 'done'" in query
	assert "assignee_id IS NOT NULL" in query
	assert "due_at <= :threshold_utc" in query
	assert params == {"threshold_utc": threshold, "limit": 10, "offset": 0}


async def test_iter_due_tasks_fetches_following_chunks_in_id_order() -> None:
	threshold = datetime(2026, 9, 8, 1, tzinfo=UTC)
	first = [_task_row(uuid.uuid4(), threshold), _task_row(uuid.uuid4(), threshold)]
	second = [_task_row(uuid.uuid4(), threshold)]
	db = _Session([first, second])

	result = [task async for task in task_repository.iter_due_tasks(db, threshold, chunk_size=2)]

	assert len(result) == 3
	assert [call[1]["offset"] for call in db.calls] == [0, 2]


async def test_iter_due_tasks_rejects_non_positive_chunk_size() -> None:
	db = _Session([])

	with pytest.raises(ValueError, match="chunk_size"):
		async for _ in task_repository.iter_due_tasks(db, datetime.now(UTC), chunk_size=0):
			pass


async def test_acquire_due_lock_allows_only_one_runner_per_slot() -> None:
	redis = _Redis()
	run_date = date(2026, 9, 7)

	results = await asyncio.gather(
		redis_lock.acquire_due_notification_lock(redis, run_date, "10", "runner-a", ttl_seconds=60),
		redis_lock.acquire_due_notification_lock(redis, run_date, "10", "runner-b", ttl_seconds=60),
	)

	assert sorted(results) == [False, True]
	assert redis.values == {"lock:notify_due:2026-09-07:10": "runner-a"} or redis.values == {
		"lock:notify_due:2026-09-07:10": "runner-b"
	}
	assert redis.ttls == {"lock:notify_due:2026-09-07:10": 60}


async def test_due_lock_uses_date_and_slot_as_distinct_keys() -> None:
	redis = _Redis()

	assert await redis_lock.acquire_due_notification_lock(redis, date(2026, 9, 7), "10", "runner", 60)
	assert await redis_lock.acquire_due_notification_lock(redis, date(2026, 9, 7), "17", "runner", 60)

	assert set(redis.values) == {
		"lock:notify_due:2026-09-07:10",
		"lock:notify_due:2026-09-07:17",
	}


async def test_due_lock_applies_key_prefix() -> None:
	redis = _Redis()

	assert await redis_lock.acquire_due_notification_lock(redis, date(2026, 9, 7), "10", "runner", 60, "ci:")
	assert redis.values == {"ci:lock:notify_due:2026-09-07:10": "runner"}


async def test_release_due_lock_does_not_delete_another_runner_lock() -> None:
	redis = _Redis()
	await redis_lock.acquire_due_notification_lock(redis, date(2026, 9, 7), "10", "runner-a", 60)

	assert not await redis_lock.release_due_notification_lock(redis, date(2026, 9, 7), "10", "runner-b")
	assert await redis_lock.release_due_notification_lock(redis, date(2026, 9, 7), "10", "runner-a")
	assert redis.values == {}

from datetime import date
from typing import Protocol


class RedisLockClient(Protocol):
	async def set(self, name: str, value: str, *, ex: int, nx: bool) -> bool | None: ...

	async def eval(self, script: str, numkeys: int, key: str, value: str) -> int: ...


LOCK_KEY_PREFIX = "lock:notify_due"
_RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


def build_due_lock_key(run_date: date, slot: str) -> str:
	return f"{LOCK_KEY_PREFIX}:{run_date.isoformat()}:{slot}"


def _validate_lock_arguments(slot: str, runner_id: str, ttl_seconds: int) -> None:
	if not slot:
		raise ValueError("slot must not be empty")
	if not runner_id:
		raise ValueError("runner_id must not be empty")
	if ttl_seconds <= 0:
		raise ValueError("ttl_seconds must be positive")


async def acquire_due_notification_lock(
	redis: RedisLockClient,
	run_date: date,
	slot: str,
	runner_id: str,
	ttl_seconds: int,
) -> bool:
	_validate_lock_arguments(slot, runner_id, ttl_seconds)
	return bool(
		await redis.set(
			build_due_lock_key(run_date, slot),
			runner_id,
			ex=ttl_seconds,
			nx=True,
		)
	)


async def release_due_notification_lock(redis: RedisLockClient, run_date: date, slot: str, runner_id: str) -> bool:
	if not slot:
		raise ValueError("slot must not be empty")
	if not runner_id:
		raise ValueError("runner_id must not be empty")

	deleted = await redis.eval(
		_RELEASE_LOCK_SCRIPT,
		1,
		build_due_lock_key(run_date, slot),
		runner_id,
	)
	return bool(deleted)


acquire = acquire_due_notification_lock
release = release_due_notification_lock

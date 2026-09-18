"""期限通知ジョブの実行枠別Redisロックを扱うrepository。

同一日付・同一実行枠（10時/17時）の重複実行を防ぐため、`SET NX EX`でロックを取得し、
解放時は`GET`で値（`runner_id`）が自分自身のものであることを確認してから`DEL`する
（02_due_notification_job.md §5）。
"""

from datetime import date
from typing import Protocol


class RedisLockClient(Protocol):
	"""ロック取得・解放に必要なRedisクライアントの最小インターフェース。"""

	async def set(self, name: str, value: str, *, ex: int, nx: bool) -> bool | None: ...

	async def eval(self, script: str, numkeys: int, key: str, value: str) -> int: ...


LOCK_KEY_PREFIX = "lock:notify_due"
_RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


def build_due_lock_key(run_date: date, slot: str, key_prefix: str = "") -> str:
	"""期限通知ロックのRedisキー`lock:notify_due:{日付}:{実行枠}`を組み立てる。

	Args:
		run_date: ロック対象日（`APP_TIMEZONE`基準のローカル日付）。
		slot: 実行枠（例: `10`/`17`）。
		key_prefix: 環境ごとにキー空間を分離するための接頭辞（`REDIS_KEY_PREFIX`）。

	Returns:
		組み立てたRedisキー文字列。
	"""
	return f"{key_prefix}{LOCK_KEY_PREFIX}:{run_date.isoformat()}:{slot}"


def _validate_lock_arguments(slot: str, runner_id: str, ttl_seconds: int) -> None:
	"""ロック取得に必要な引数の必須チェックを行う。

	Args:
		slot: 実行枠。空文字は不可。
		runner_id: ロック所有者を識別するID。空文字は不可。
		ttl_seconds: ロックのTTL秒数。正の値であること。

	Raises:
		ValueError: いずれかの引数が不正な場合。
	"""
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
	key_prefix: str = "",
) -> bool:
	"""期限通知ジョブの実行枠別ロックを`SET NX EX`で取得する。

	Args:
		redis: ロック操作対象のRedisクライアント。
		run_date: ロック対象日（ローカル日付）。
		slot: 実行枠。
		runner_id: 呼び出し元プロセスを識別するランナーID。解放時の所有者確認に使う。
		ttl_seconds: ロックのTTL秒数（`NOTIFY_DUE_LOCK_TTL_SECONDS`）。
		key_prefix: Redisキー空間の接頭辞。

	Returns:
		取得に成功した場合`True`、既に他プロセスが保持している場合`False`。

	Raises:
		ValueError: `slot`/`runner_id`が空、または`ttl_seconds`が0以下の場合。
	"""
	_validate_lock_arguments(slot, runner_id, ttl_seconds)
	return bool(
		await redis.set(
			build_due_lock_key(run_date, slot, key_prefix),
			runner_id,
			ex=ttl_seconds,
			nx=True,
		)
	)


async def release_due_notification_lock(
	redis: RedisLockClient, run_date: date, slot: str, runner_id: str, key_prefix: str = ""
) -> bool:
	"""失敗時に限り、所有者確認後にロックを解放する。

	成功時はロックを解放せずTTLまで保持し、同一実行枠の再実行を抑止する
	（呼び出し元の`due_notification_job`が成否で解放要否を判断する）。

	Args:
		redis: ロック操作対象のRedisクライアント。
		run_date: ロック対象日。
		slot: 実行枠。
		runner_id: 取得時に使用したランナーID。値が一致する場合のみ削除する。
		key_prefix: Redisキー空間の接頭辞。

	Returns:
		自分が所有するロックを削除できた場合`True`、値が一致せず削除しなかった場合`False`。

	Raises:
		ValueError: `slot`/`runner_id`が空の場合。
	"""
	if not slot:
		raise ValueError("slot must not be empty")
	if not runner_id:
		raise ValueError("runner_id must not be empty")

	deleted = await redis.eval(
		_RELEASE_LOCK_SCRIPT,
		1,
		build_due_lock_key(run_date, slot, key_prefix),
		runner_id,
	)
	return bool(deleted)


acquire = acquire_due_notification_lock
release = release_due_notification_lock

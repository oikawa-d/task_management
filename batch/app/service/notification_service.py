"""期限通知の作成をチャンク単位で行うservice。

repository層のON CONFLICT DO NOTHINGと組み合わせ、チャンクごとにコミットすることで
一部失敗時も確定済み分を保持する（02_due_notification_job.md §6・§11）。
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository import notification_repository

NOTIFICATION_TYPE = "due_soon_batch"
NOTIFICATION_BODY = "期限が近いタスクです"


@dataclass(frozen=True)
class DueTask:
	"""通知作成の入力として使うタスクのスナップショット（`task_repository.DueTask`から変換）。"""

	id: uuid.UUID
	title: str
	assignee_id: uuid.UUID
	due_at: datetime


async def bulk_create_due_notifications(
	db: AsyncSession,
	tasks: Sequence[DueTask],
	run_date: date,
	notification_slot: str,
	chunk_size: int,
) -> int:
	"""期限通知対象タスクを`chunk_size`件ずつ通知へ変換し、チャンクごとにコミットしながら作成する。

	チャンク内で例外が発生した場合はそのチャンクをロールバックして再送出する。既にコミット済みの
	チャンクは維持されるため、`dedupe_key`のDB一意制約により再実行時の重複作成は起きない。

	Args:
		db: 呼び出し元が管理するAsyncSession。チャンクごとに`commit`/`rollback`する。
		tasks: 通知作成対象のタスク一覧。
		run_date: 実行日（`dedupe_key`の日付部分・`APP_TIMEZONE`基準）。
		notification_slot: 実行枠（`dedupe_key`の枠部分）。
		chunk_size: 1トランザクションで処理する件数。

	Returns:
		実際に作成できた通知件数の合計（既存行のためスキップされた件数は含まない）。

	Raises:
		ValueError: `chunk_size`が0以下の場合。
		Exception: repository呼び出しで発生した例外をロールバック後に再送出する。
	"""
	if chunk_size <= 0:
		raise ValueError("chunk_size must be positive")

	created_count = 0
	for start in range(0, len(tasks), chunk_size):
		chunk = tasks[start : start + chunk_size]
		payloads = [_to_notification_payload(task, run_date, notification_slot) for task in chunk]
		try:
			created_count += await notification_repository.bulk_create_if_absent(db, payloads)
			await db.commit()
		except Exception:
			await db.rollback()
			raise
	return created_count


def _to_notification_payload(task: DueTask, run_date: date, notification_slot: str) -> dict[str, object]:
	"""1タスクを`notifications`のINSERT用ペイロードへ変換する。

	`dedupe_key`は`batch:{run_date}:{notification_slot}:{task.id}`とし、同一タスク・同一実行枠の
	重複通知をDB一意制約で防ぐ（02_due_notification_job.md §4）。

	Args:
		task: 変換元のタスク。
		run_date: 実行日。
		notification_slot: 実行枠。

	Returns:
		`notification_repository.bulk_create_if_absent`へ渡す1行分の辞書。
	"""
	return {
		"user_id": task.assignee_id,
		"task_id": task.id,
		"type": NOTIFICATION_TYPE,
		"title": task.title,
		"body": NOTIFICATION_BODY,
		"due_at": task.due_at,
		"dedupe_key": f"batch:{run_date.isoformat()}:{notification_slot}:{task.id}",
	}

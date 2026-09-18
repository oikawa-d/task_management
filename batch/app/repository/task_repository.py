"""期限通知対象タスクの抽出を担うrepository。

`tasks`テーブルから未完了・担当者あり・期限あり・閾値以下の行をチャンク単位で取得する
（02_due_notification_job.md §4）。
"""

import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class DueTask:
	"""期限通知対象として抽出したタスク1件のスナップショット。"""

	id: uuid.UUID
	project_id: uuid.UUID | None
	title: str
	assignee_id: uuid.UUID
	due_at: datetime


_DUE_TASK_QUERY = text(
	"SELECT id, project_id, title, assignee_id, due_at "
	"FROM tasks "
	"WHERE status <> 'done' "
	"AND assignee_id IS NOT NULL "
	"AND due_at IS NOT NULL "
	"AND due_at <= :threshold_utc "
	"ORDER BY id "
	"LIMIT :limit OFFSET :offset"
)


def _map_due_task(row: Mapping[str, Any]) -> DueTask:
	"""SELECT結果の1行を`DueTask`へ変換する。

	Args:
		row: `_DUE_TASK_QUERY`の結果行（列名でアクセス可能なMapping）。

	Returns:
		変換した`DueTask`。
	"""
	return DueTask(
		id=cast(uuid.UUID, row["id"]),
		project_id=cast(uuid.UUID | None, row["project_id"]),
		title=cast(str, row["title"]),
		assignee_id=cast(uuid.UUID, row["assignee_id"]),
		due_at=cast(datetime, row["due_at"]),
	)


async def iter_due_tasks(db: AsyncSession, threshold_utc: datetime, chunk_size: int) -> AsyncIterator[DueTask]:
	"""`due_at <= threshold_utc`の未完了・担当者ありタスクを`chunk_size`件ずつ抽出する。

	`OFFSET`によるページングで全件を1トランザクションに保持せず、チャンクごとに
	呼び出し元がコミットできるようにする（02_due_notification_job.md §11）。

	Args:
		db: 参照専用に使うAsyncSession。
		threshold_utc: 抽出上限となるUTC日時（`due_at <= threshold_utc`、境界値を含む）。
		chunk_size: 1回のSELECTで取得する件数。

	Yields:
		条件に一致する`DueTask`を`id`昇順で順次返す。

	Raises:
		ValueError: `chunk_size`が0以下の場合。
		sqlalchemy.exc.SQLAlchemyError: SELECT失敗時。
	"""
	if chunk_size <= 0:
		raise ValueError("chunk_size must be positive")

	offset = 0
	while True:
		result = await db.execute(
			_DUE_TASK_QUERY,
			{"threshold_utc": threshold_utc, "limit": chunk_size, "offset": offset},
		)
		rows = result.mappings().all()
		for row in rows:
			yield _map_due_task(cast(Mapping[str, Any], row))

		if len(rows) < chunk_size:
			break
		offset += len(rows)

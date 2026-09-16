import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class DueTask:
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
	return DueTask(
		id=cast(uuid.UUID, row["id"]),
		project_id=cast(uuid.UUID | None, row["project_id"]),
		title=cast(str, row["title"]),
		assignee_id=cast(uuid.UUID, row["assignee_id"]),
		due_at=cast(datetime, row["due_at"]),
	)


async def iter_due_tasks(db: AsyncSession, threshold_utc: datetime, chunk_size: int) -> AsyncIterator[DueTask]:
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

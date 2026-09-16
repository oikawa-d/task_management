from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def bulk_create_if_absent(db: AsyncSession, payloads: Sequence[dict[str, object]]) -> int:
	if not payloads:
		return 0

	statement = (
		insert(Notification).values(list(payloads)).on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
	)
	result = await db.execute(statement)
	return result.rowcount or 0

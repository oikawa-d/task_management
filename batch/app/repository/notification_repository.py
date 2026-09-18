"""`notifications`テーブルへの通知一括作成を担うrepository。"""

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def bulk_create_if_absent(db: AsyncSession, payloads: Sequence[dict[str, object]]) -> int:
	"""通知を一括INSERTし、`(user_id, dedupe_key)`が既存の行は無視する。

	`ON CONFLICT DO NOTHING`によりDB側の一意制約で重複防止を行うため、
	Redisロック取得漏れや同一実行枠の再実行でも同じ通知を二重作成しない
	（02_due_notification_job.md §5）。

	Args:
		db: 呼び出し元が管理するAsyncSession。コミットは呼び出し元の責務。
		payloads: `notifications`の1行分の値を表す辞書のシーケンス。空の場合は何もしない。

	Returns:
		実際にINSERTされた件数（既存行のためスキップされた件数は含まない）。

	Raises:
		sqlalchemy.exc.SQLAlchemyError: INSERT失敗時。
	"""
	if not payloads:
		return 0

	statement = (
		insert(Notification).values(list(payloads)).on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
	)
	result = await db.execute(statement)
	return result.rowcount or 0

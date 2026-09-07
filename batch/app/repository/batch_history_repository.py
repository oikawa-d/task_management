import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 12_table_batch_history.md §4により、開始/完了/失敗の単純なINSERT・UPDATEは
# 業務ロジックを伴わないため直接SQLでよい（00_policy.md §2.1の例外ではなく、
# 本テーブル詳細設計書自身が明記する個別の設計判断）。保持期間パージのみSP経由とする。


async def start(db: AsyncSession, batch_name: str, trigger_type: str, slot: str | None) -> uuid.UUID:
	result = await db.execute(
		text(
			"INSERT INTO batch_history (run_id, batch_name, trigger_type, slot) "
			"VALUES (gen_random_uuid(), :batch_name, :trigger_type, :slot) RETURNING run_id"
		),
		{"batch_name": batch_name, "trigger_type": trigger_type, "slot": slot},
	)
	run_id: uuid.UUID = result.scalar_one()
	return run_id


async def complete(
	db: AsyncSession, run_id: uuid.UUID, target_count: int, success_count: int, skipped_count: int
) -> None:
	await db.execute(
		text(
			"UPDATE batch_history SET status = 'complete', ended_at = now(), "
			"target_count = :target_count, success_count = :success_count, skipped_count = :skipped_count "
			"WHERE run_id = :run_id"
		),
		{
			"run_id": run_id,
			"target_count": target_count,
			"success_count": success_count,
			"skipped_count": skipped_count,
		},
	)


async def fail(
	db: AsyncSession,
	run_id: uuid.UUID,
	error_code: str | None,
	error_detail: str | None,
	target_count: int,
	success_count: int,
	skipped_count: int,
) -> None:
	await db.execute(
		text(
			"UPDATE batch_history SET status = 'error', ended_at = now(), "
			"error_code = :error_code, error_detail = :error_detail, "
			"target_count = :target_count, success_count = :success_count, skipped_count = :skipped_count "
			"WHERE run_id = :run_id"
		),
		{
			"run_id": run_id,
			"error_code": error_code,
			"error_detail": error_detail,
			"target_count": target_count,
			"success_count": success_count,
			"skipped_count": skipped_count,
		},
	)


async def purge_expired(db: AsyncSession, retention_days: int) -> None:
	await db.execute(text("CALL sp_purge_batch_history(:retention_days)"), {"retention_days": retention_days})

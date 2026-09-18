"""`batch_history`テーブルへのアクセスを担うrepository。

ジョブ実行1回ごとの開始・正常終了・失敗の記録と、保持期間を超えた行のパージを行う。
12_table_batch_history.md §4により、開始/完了/失敗の単純なINSERT・UPDATEは
業務ロジックを伴わないため直接SQLでよい（00_policy.md §2.1の例外ではなく、
本テーブル詳細設計書自身が明記する個別の設計判断）。保持期間パージのみSP経由とする。
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def start(db: AsyncSession, batch_name: str, trigger_type: str, slot: str | None) -> uuid.UUID:
	"""ジョブ実行開始時に`batch_history`へ`inprogress`行をINSERTする。

	Args:
		db: 呼び出し元が管理するAsyncSession。コミットは呼び出し元の責務。
		batch_name: ジョブ種別を表す名前（例: `due_notification`）。
		trigger_type: 起動契機（`scheduled`等）。
		slot: 実行枠（例: 10時/17時の`slot`）。存在しないジョブでは`None`。

	Returns:
		採番された`run_id`。以降の`complete`/`fail`呼び出しで同一実行を紐付けるために使う。

	Raises:
		sqlalchemy.exc.SQLAlchemyError: INSERT失敗時。
	"""
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
	"""ジョブ正常終了時に`batch_history`を`complete`へ更新し、終了時刻・件数を記録する。

	Args:
		db: 呼び出し元が管理するAsyncSession。コミットは呼び出し元の責務。
		run_id: `start`で採番された実行ID。
		target_count: 処理対象として抽出した件数。
		success_count: 実際に作成・処理できた件数。
		skipped_count: ロック未取得等でスキップした件数。

	Raises:
		sqlalchemy.exc.SQLAlchemyError: UPDATE失敗時。
	"""
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
	"""ジョブ失敗時に`batch_history`を`error`へ更新し、エラー内容と終了時刻を記録する。

	Args:
		db: 呼び出し元が管理するAsyncSession。コミットは呼び出し元の責務。
		run_id: `start`で採番された実行ID。
		error_code: エラー種別を表すコード。不明な場合は`None`。
		error_detail: エラー詳細メッセージ。不明な場合は`None`。
		target_count: 失敗までに処理対象として抽出できた件数。
		success_count: 失敗までに作成・処理できた件数。
		skipped_count: 失敗までにスキップした件数。

	Raises:
		sqlalchemy.exc.SQLAlchemyError: UPDATE失敗時。この場合、呼び出し元は
			ジョブ結果を上書きせずログのみを残す（02_due_notification_job.md §6）。
	"""
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
	"""保持期間を超えた`batch_history`行をストアドプロシージャ`sp_purge_batch_history`でパージする。

	Args:
		db: 呼び出し元が管理するAsyncSession。コミットは呼び出し元の責務。
		retention_days: `started_at`基準の保持日数（`BATCH_HISTORY_RETENTION_DAYS`）。

	Raises:
		sqlalchemy.exc.SQLAlchemyError: プロシージャ呼び出し失敗時。
	"""
	await db.execute(text("CALL sp_purge_batch_history(:retention_days)"), {"retention_days": retention_days})

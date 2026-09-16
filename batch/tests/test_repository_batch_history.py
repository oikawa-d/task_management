from app.repository import batch_history_repository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_start_creates_inprogress_history(db_session: AsyncSession) -> None:
	run_id = await batch_history_repository.start(db_session, "due_notification", "scheduled", "10")

	row = (
		(
			await db_session.execute(
				text("SELECT status, ended_at, batch_name, slot FROM batch_history WHERE run_id = :run_id"),
				{"run_id": run_id},
			)
		)
		.mappings()
		.one()
	)
	assert row["status"] == "inprogress"
	assert row["ended_at"] is None
	assert row["batch_name"] == "due_notification"
	assert row["slot"] == "10"


async def test_complete_updates_history_to_complete(db_session: AsyncSession) -> None:
	run_id = await batch_history_repository.start(db_session, "due_notification", "scheduled", "17")

	await batch_history_repository.complete(db_session, run_id, target_count=5, success_count=4, skipped_count=1)

	row = (
		(
			await db_session.execute(
				text(
					"SELECT status, ended_at, target_count, success_count, skipped_count "
					"FROM batch_history WHERE run_id = :run_id"
				),
				{"run_id": run_id},
			)
		)
		.mappings()
		.one()
	)
	assert row["status"] == "complete"
	assert row["ended_at"] is not None
	assert row["target_count"] == 5
	assert row["success_count"] == 4
	assert row["skipped_count"] == 1


async def test_fail_updates_error_history(db_session: AsyncSession) -> None:
	run_id = await batch_history_repository.start(db_session, "due_notification", "manual", None)

	await batch_history_repository.fail(
		db_session,
		run_id,
		error_code="INTERNAL_ERROR",
		error_detail="unexpected exception",
		target_count=3,
		success_count=1,
		skipped_count=0,
	)

	row = (
		(
			await db_session.execute(
				text("SELECT status, ended_at, error_code, error_detail FROM batch_history WHERE run_id = :run_id"),
				{"run_id": run_id},
			)
		)
		.mappings()
		.one()
	)
	assert row["status"] == "error"
	assert row["ended_at"] is not None
	assert row["error_code"] == "INTERNAL_ERROR"
	assert row["error_detail"] == "unexpected exception"


async def test_purge_expired_deletes_only_old_rows(db_session: AsyncSession) -> None:
	old_run_id = (
		await db_session.execute(
			text(
				"INSERT INTO batch_history (run_id, batch_name, trigger_type, status, started_at, ended_at) "
				"VALUES (gen_random_uuid(), 'due_notification', 'scheduled', 'complete', "
				"now() - interval '40 days', now() - interval '40 days') RETURNING run_id"
			)
		)
	).scalar_one()
	recent_run_id = await batch_history_repository.start(db_session, "due_notification", "scheduled", "10")

	await batch_history_repository.purge_expired(db_session, retention_days=30)

	remaining_ids = (await db_session.execute(text("SELECT run_id FROM batch_history"))).scalars().all()
	assert old_run_id not in remaining_ids
	assert recent_run_id in remaining_ids

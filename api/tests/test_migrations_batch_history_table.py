import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _start(db: AsyncSession, run_id: uuid.UUID) -> None:
	await db.execute(
		text(
			"INSERT INTO batch_history (run_id, batch_name, trigger_type) "
			"VALUES (:run_id, 'due_notification', 'scheduled')"
		),
		{"run_id": run_id},
	)


async def test_batch_history_run_id_is_unique(db_session: AsyncSession) -> None:
	run_id = uuid.uuid4()
	await _start(db_session, run_id)

	with pytest.raises(IntegrityError):
		await _start(db_session, run_id)


async def test_batch_history_inprogress_requires_null_end(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO batch_history (run_id, batch_name, trigger_type, status, ended_at) "
				"VALUES (:run_id, 'due_notification', 'scheduled', 'inprogress', now())"
			),
			{"run_id": uuid.uuid4()},
		)


async def test_batch_history_complete_requires_no_error_fields(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO batch_history (run_id, batch_name, trigger_type, status, ended_at, error_code) "
				"VALUES (:run_id, 'due_notification', 'scheduled', 'complete', now(), 'X')"
			),
			{"run_id": uuid.uuid4()},
		)


async def test_batch_history_trigger_type_check_rejects_invalid_value(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO batch_history (run_id, batch_name, trigger_type) "
				"VALUES (:run_id, 'due_notification', 'cron')"
			),
			{"run_id": uuid.uuid4()},
		)


async def test_batch_history_ended_at_must_not_precede_started_at(db_session: AsyncSession) -> None:
	with pytest.raises(DBAPIError):
		await db_session.execute(
			text(
				"INSERT INTO batch_history (run_id, batch_name, trigger_type, status, started_at, ended_at) "
				"VALUES (:run_id, 'due_notification', 'scheduled', 'complete', now(), now() - interval '1 hour')"
			),
			{"run_id": uuid.uuid4()},
		)


async def test_trg_batch_history_set_updated_at(db_session: AsyncSession) -> None:
	run_id = uuid.uuid4()
	await _start(db_session, run_id)
	await db_session.commit()

	before = (
		await db_session.execute(
			text("SELECT updated_at FROM batch_history WHERE run_id = :run_id"), {"run_id": run_id}
		)
	).scalar_one()
	await db_session.execute(
		text("UPDATE batch_history SET status = 'complete', ended_at = now() WHERE run_id = :run_id"),
		{"run_id": run_id},
	)
	after = (
		await db_session.execute(
			text("SELECT updated_at FROM batch_history WHERE run_id = :run_id"), {"run_id": run_id}
		)
	).scalar_one()

	assert after > before

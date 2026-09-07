from app.models.batch_history import BatchHistory
from app.repository import batch_history_repository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def test_batch_history_model_maps_inserted_row(db_session: AsyncSession) -> None:
	run_id = await batch_history_repository.start(db_session, "due_notification", "scheduled", "10")

	result = await db_session.execute(select(BatchHistory).where(BatchHistory.run_id == run_id))
	history = result.scalars().one()

	assert history.batch_name == "due_notification"
	assert history.trigger_type == "scheduled"
	assert history.slot == "10"
	assert history.status == "inprogress"
	assert history.ended_at is None

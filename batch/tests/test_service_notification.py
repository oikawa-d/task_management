import uuid
from datetime import date, datetime, timezone

import pytest
from app.service.notification_service import DueTask, bulk_create_due_notifications


@pytest.mark.asyncio
async def test_bulk_create_due_notifications_builds_slot_scoped_dedupe_key(monkeypatch: pytest.MonkeyPatch) -> None:
	created_payloads: list[dict[str, object]] = []

	class FakeSession:
		async def commit(self) -> None:
			return None

	async def fake_bulk_create(_db, payloads: list[dict[str, object]]) -> int:
		created_payloads.extend(payloads)
		return len(payloads)

	monkeypatch.setattr(
		"app.service.notification_service.notification_repository.bulk_create_if_absent",
		fake_bulk_create,
	)
	task_id = uuid.uuid4()
	assignee_id = uuid.uuid4()
	task = DueTask(
		id=task_id,
		title="期限タスク",
		assignee_id=assignee_id,
		due_at=datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc),
	)

	created = await bulk_create_due_notifications(
		FakeSession(),
		[task],
		run_date=date(2026, 9, 7),
		notification_slot="10",
		chunk_size=10,
	)

	assert created == 1
	assert created_payloads == [
		{
			"user_id": assignee_id,
			"task_id": task_id,
			"type": "due_soon_batch",
			"title": "期限タスク",
			"body": "期限が近いタスクです",
			"due_at": task.due_at,
			"dedupe_key": f"batch:2026-09-07:10:{task_id}",
		}
	]


@pytest.mark.asyncio
async def test_bulk_create_due_notifications_commits_each_configured_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
	commit_count = 0
	call_sizes: list[int] = []

	class FakeSession:
		async def commit(self) -> None:
			nonlocal commit_count
			commit_count += 1

	async def fake_bulk_create(_db, payloads: list[dict[str, object]]) -> int:
		call_sizes.append(len(payloads))
		return len(payloads)

	monkeypatch.setattr(
		"app.service.notification_service.notification_repository.bulk_create_if_absent",
		fake_bulk_create,
	)
	tasks = [DueTask(uuid.uuid4(), f"task-{index}", uuid.uuid4(), datetime.now(timezone.utc)) for index in range(3)]

	created = await bulk_create_due_notifications(FakeSession(), tasks, date(2026, 9, 7), "17", chunk_size=2)

	assert created == 3
	assert call_sizes == [2, 1]
	assert commit_count == 2


@pytest.mark.asyncio
async def test_bulk_create_due_notifications_rolls_back_failed_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
	rollback_count = 0

	class FakeSession:
		async def commit(self) -> None:
			raise RuntimeError("insert failed")

		async def rollback(self) -> None:
			nonlocal rollback_count
			rollback_count += 1

	async def fake_bulk_create(_db, _payloads: list[dict[str, object]]) -> int:
		return 0

	monkeypatch.setattr(
		"app.service.notification_service.notification_repository.bulk_create_if_absent",
		fake_bulk_create,
	)

	with pytest.raises(RuntimeError, match="insert failed"):
		await bulk_create_due_notifications(
			FakeSession(),
			[DueTask(uuid.uuid4(), "task", uuid.uuid4(), datetime.now(timezone.utc))],
			date(2026, 9, 7),
			"10",
			chunk_size=1,
		)

	assert rollback_count == 1

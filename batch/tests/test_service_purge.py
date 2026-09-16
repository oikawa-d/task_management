from unittest.mock import AsyncMock

import pytest
from app.service.purge_service import purge_notifications


@pytest.mark.asyncio
async def test_purge_notifications_delegates_retention_days(monkeypatch: pytest.MonkeyPatch) -> None:
	purge = AsyncMock()
	commit = AsyncMock()

	class FakeSession:
		async def commit(self) -> None:
			await commit()

		async def rollback(self) -> None:
			raise AssertionError("rollback must not be called")

	monkeypatch.setattr("app.service.purge_service.purge_repository.purge_notifications", purge)

	session = FakeSession()
	await purge_notifications(session, retention_days=90)

	purge.assert_awaited_once_with(session, retention_days=90)
	commit.assert_awaited_once()

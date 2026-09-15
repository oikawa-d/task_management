"""通知更新APIがHTTPレスポンス後に変更を永続化することを実DBで検証する。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
from app.api.routers import notifications_router
from app.auth.base import AuthContext
from app.auth.factory import get_auth_strategy
from app.core import deps
from app.core.config import get_backend_settings
from app.core.exceptions import register_error_handling
from app.db import get_db_session
from app.repository import notification_repository, user_repository
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class _AuthenticatedStrategy:
	mode = "jwt"

	def __init__(self, user_id: UUID) -> None:
		self.user_id = user_id

	async def authenticate(self, _request: object) -> AuthContext:
		return AuthContext(user_id=self.user_id)


async def _insert_notification(db: AsyncSession, user_id: UUID, dedupe_key: str) -> UUID:
	result = await db.execute(
		text(
			"INSERT INTO notifications "
			"(user_id, type, title, body, dedupe_key) "
			"VALUES (:user_id, 'due_today_created', :title, :body, :dedupe_key) "
			"RETURNING id"
		),
		{"user_id": user_id, "title": dedupe_key, "body": "確認してください", "dedupe_key": dedupe_key},
	)
	return result.scalar_one()


@pytest.mark.asyncio
async def test_notification_mutations_persist_after_http_response(
	db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
	username = f"notification-http-{uuid4().hex[:8]}"
	user_id = await user_repository.create(db_session, username, f"{username}@example.com", "hash")
	first_id = await _insert_notification(db_session, user_id, f"http-first-{uuid4().hex}")
	second_id = await _insert_notification(db_session, user_id, f"http-second-{uuid4().hex}")
	await db_session.commit()

	engine = create_async_engine(get_backend_settings().database_url)
	session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
	app = FastAPI()
	register_error_handling(app)
	app.include_router(notifications_router.router)
	app.dependency_overrides[get_auth_strategy] = lambda: _AuthenticatedStrategy(user_id)

	async def _get_real_db_session() -> AsyncIterator[AsyncSession]:
		async with session_factory() as session:
			yield session

	app.dependency_overrides[get_db_session] = _get_real_db_session
	monkeypatch.setattr(deps.redis_store, "check_rate_limit", AsyncMock(return_value=1))
	try:
		transport = httpx.ASGITransport(app=app)
		async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
			read_response = await client.patch(f"/api/notifications/{first_id}/read")
			assert read_response.status_code == 200
			assert read_response.json()["unread_count"] == 1

			async with session_factory() as verification_session:
				read_at = await verification_session.scalar(
					text("SELECT read_at FROM notifications WHERE id = :id"), {"id": first_id}
				)
				assert read_at is not None
				assert await notification_repository.count_unread(verification_session, user_id) == 1

			read_all_response = await client.post("/api/notifications/read-all")
			assert read_all_response.status_code == 200
			assert read_all_response.json() == {"updated_count": 1, "unread_count": 0}

			async with session_factory() as verification_session:
				read_at_values = (
					await verification_session.scalars(
						text("SELECT read_at FROM notifications WHERE id IN (:first_id, :second_id)"),
						{"first_id": first_id, "second_id": second_id},
					)
				).all()
				assert all(value is not None for value in read_at_values)
				assert await notification_repository.count_unread(verification_session, user_id) == 0
	finally:
		app.dependency_overrides.clear()
		await engine.dispose()

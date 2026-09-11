from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.core.config import BackendSettings
from app.core.exceptions import TooManyAttemptsError
from app.service import auth_service


def _settings(**overrides: object) -> BackendSettings:
	base = get_test_settings_defaults()
	base.update(overrides)
	return BackendSettings(**base)


def get_test_settings_defaults() -> dict[str, object]:
	return {
		"database_url": "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test",
		"jwt_secret_key": "test-jwt-secret-key",
		"google_client_id": "test-google-client-id",
		"google_client_secret": "test-google-client-secret",
		"initial_admin_email": "admin@example.com",
		"initial_admin_username": "admin",
		"initial_admin_password": "test-admin-password",
		"login_max_attempts": 5,
		"login_lock_window_seconds": 900,
	}


async def test_ensure_login_not_rate_limited_passes_when_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
	get_count = AsyncMock(return_value=4)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", get_count)

	await auth_service.ensure_login_not_rate_limited("user@example.com", "127.0.0.1", _settings())

	get_count.assert_awaited_once_with("user@example.com", "127.0.0.1")


async def test_ensure_login_not_rate_limited_raises_too_many_attempts_at_limit(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=5))
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_ttl", AsyncMock(return_value=321))

	with pytest.raises(TooManyAttemptsError) as raised:
		await auth_service.ensure_login_not_rate_limited("user@example.com", "127.0.0.1", _settings())

	assert raised.value.retry_after == 321


async def test_record_login_failure_increments_with_configured_window(monkeypatch: pytest.MonkeyPatch) -> None:
	incr = AsyncMock(return_value=3)
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", incr)

	count = await auth_service.record_login_failure("user@example.com", "127.0.0.1", _settings())

	assert count == 3
	incr.assert_awaited_once_with("user@example.com", "127.0.0.1", 900)


async def test_record_login_success_resets_failure_counter(monkeypatch: pytest.MonkeyPatch) -> None:
	reset = AsyncMock(return_value=None)
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", reset)

	await auth_service.record_login_success("user@example.com", "127.0.0.1")

	reset.assert_awaited_once_with("user@example.com", "127.0.0.1")

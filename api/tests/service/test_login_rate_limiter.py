"""app.service.auth_service におけるログイン試行回数制限(レート制限)機能のテスト。

redis_storeをモック化し、実際のRedis接続を行わずに、
失敗回数の判定・上限超過時の例外送出・失敗/成功時のカウンタ更新呼び出しを検証する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.core.config import BackendSettings
from app.core.exceptions import TooManyAttemptsError
from app.service import auth_service


def _settings(**overrides: object) -> BackendSettings:
	"""デフォルト値に任意の上書き値を適用したBackendSettingsを生成するヘルパー。

	Args:
		**overrides: デフォルト設定値に対して上書きしたいキーと値。

	Returns:
		上書き後の値で構築されたBackendSettingsインスタンス。
	"""
	base = get_test_settings_defaults()
	base.update(overrides)
	return BackendSettings(**base)


def get_test_settings_defaults() -> dict[str, object]:
	"""BackendSettings生成に必要なデフォルトのテスト用設定値を返す。

	Returns:
		DB接続情報・JWT鍵・Google OAuth情報・初期管理者情報・
		ログイン試行回数制限の閾値などを含む設定値の辞書。
	"""
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
	"""失敗回数が上限未満(4回、上限5回)の場合に、例外を送出せず正常に通過することを検証する。"""
	get_count = AsyncMock(return_value=4)
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", get_count)

	await auth_service.ensure_login_not_rate_limited("user@example.com", "127.0.0.1", _settings())

	get_count.assert_awaited_once_with("user@example.com", "127.0.0.1")


async def test_ensure_login_not_rate_limited_raises_too_many_attempts_at_limit(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""失敗回数が上限(5回)に達した場合にTooManyAttemptsErrorが送出され、retry_afterにTTL値が設定されることを検証する。"""
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_count", AsyncMock(return_value=5))
	monkeypatch.setattr(auth_service.redis_store, "get_login_failure_ttl", AsyncMock(return_value=742))

	with pytest.raises(TooManyAttemptsError) as exc_info:
		await auth_service.ensure_login_not_rate_limited("user@example.com", "127.0.0.1", _settings())

	assert exc_info.value.retry_after == 742


async def test_record_login_failure_increments_with_configured_window(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ログイン失敗記録時に、設定されたロック時間窓(秒数)を渡して失敗回数をインクリメントし、その値を返すことを検証する。"""
	incr = AsyncMock(return_value=3)
	monkeypatch.setattr(auth_service.redis_store, "incr_login_failure", incr)

	count = await auth_service.record_login_failure("user@example.com", "127.0.0.1", _settings())

	assert count == 3
	incr.assert_awaited_once_with("user@example.com", "127.0.0.1", 900)


async def test_record_login_success_resets_failure_counter(monkeypatch: pytest.MonkeyPatch) -> None:
	"""ログイン成功記録時に、失敗回数カウンタがリセットされることを検証する。"""
	reset = AsyncMock(return_value=None)
	monkeypatch.setattr(auth_service.redis_store, "reset_login_failure", reset)

	await auth_service.record_login_success("user@example.com", "127.0.0.1")

	reset.assert_awaited_once_with("user@example.com", "127.0.0.1")

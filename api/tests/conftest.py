import os

import pytest

_REQUIRED_ENV_DEFAULTS = {
	"DATABASE_URL": "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test",
	"REDIS_URL": "redis://localhost:6379/1",
	"JWT_SECRET_KEY": "test-jwt-secret-key",
	"GOOGLE_CLIENT_ID": "test-google-client-id",
	"GOOGLE_CLIENT_SECRET": "test-google-client-secret",
	"INITIAL_ADMIN_EMAIL": "admin@example.com",
	"INITIAL_ADMIN_USERNAME": "admin",
	"INITIAL_ADMIN_PASSWORD": "test-admin-password",
}

for key, value in _REQUIRED_ENV_DEFAULTS.items():
	os.environ.setdefault(key, value)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
	from app.core.config import get_backend_settings

	get_backend_settings.cache_clear()
	yield
	get_backend_settings.cache_clear()

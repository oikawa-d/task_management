import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
	from app.core.config import get_backend_settings

	get_backend_settings.cache_clear()
	yield
	get_backend_settings.cache_clear()

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
	model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

	app_env: Literal["local", "ci", "production"] = "local"
	log_level: str = "INFO"

	database_url: str
	database_pool_size: int = 5
	database_max_overflow: int = 10
	redis_url: str = "redis://redis:6379/0"

	auth_mode: Literal["session", "jwt"] = "session"
	health_check_timeout_seconds: float = 2

	enable_api_docs: bool = True


@lru_cache
def get_backend_settings() -> BackendSettings:
	return BackendSettings()

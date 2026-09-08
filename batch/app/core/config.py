from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BatchSettings(BaseSettings):
	model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

	log_level: str = "INFO"

	database_url: str
	redis_url: str = "redis://redis:6379/0"

	app_timezone: str = "Asia/Tokyo"
	notify_due_run_hours: str = "10,17"
	notify_due_cron_minute: int = 0
	notify_due_target_hour: int = 10
	notify_due_lock_ttl_seconds: int = 82800
	notify_due_batch_chunk_size: int = 500
	notification_retention_days: int = 90
	api_history_retention_days: int = 30
	batch_history_retention_days: int = 30
	batch_enabled: bool = True


@lru_cache
def get_batch_settings() -> BatchSettings:
	return BatchSettings()

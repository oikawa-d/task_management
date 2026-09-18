"""batchプロセスの環境変数設定を定義するモジュール。

pydantic-settingsを用いて`.env`および環境変数からbatch設定を読み込み、
スケジューラ・DB・Redis・通知ジョブが共通で参照する設定値を提供する。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BatchSettings(BaseSettings):
	"""batchプロセス全体で使用する環境変数設定。

	`.env`ファイルおよび環境変数（大文字小文字を区別しない）から値を読み込む。
	定義されていない環境変数は無視する（`extra="ignore"`）。
	"""

	model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

	log_level: str = "INFO"

	database_url: str
	redis_url: str = "redis://redis:6379/0"
	redis_key_prefix: str = ""
	redis_test_db: int = 1

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
	"""batch設定のシングルトンインスタンスを返す。

	`lru_cache`によりプロセス内で初回呼び出し時のみ`BatchSettings`を生成し、
	以降は同一インスタンスを再利用することで環境変数の再読み込みを避ける。

	Returns:
		読み込み済みの`BatchSettings`インスタンス。

	Raises:
		pydantic.ValidationError: 必須の環境変数（`database_url`等）が未設定の場合。
	"""
	return BatchSettings()

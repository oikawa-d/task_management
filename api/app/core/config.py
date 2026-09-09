from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AuthMode = Literal["session", "jwt"]


class BackendSettings(BaseSettings):
	model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

	# 共通・ポート
	app_env: Literal["local", "ci", "production"] = "local"
	log_level: str = "INFO"

	# データストア
	database_url: str
	database_pool_size: int = 5
	database_max_overflow: int = 10
	redis_url: str = "redis://redis:6379/0"
	redis_key_prefix: str = ""
	redis_test_db: int = 1
	login_history_retention_days: int = 90
	api_history_retention_days: int = 30
	batch_history_retention_days: int = 30
	api_history_body_max_bytes: int = 65536
	api_history_error_detail_max_length: int = 4000

	# 認証共通・session方式
	auth_mode: AuthMode = "session"
	session_ttl_seconds: int = 1800
	session_absolute_ttl_seconds: int = 28800
	cookie_name_session: str = "cerberus_sid"
	cookie_name_csrf: str = "cerberus_csrf"
	cookie_name_oauth_state: str = "cerberus_oauth_state"
	cookie_secure: bool = False
	cookie_samesite: Literal["lax", "strict", "none"] = "lax"
	cookie_domain: str = ""
	login_max_attempts: int = 5
	login_lock_window_seconds: int = 900
	rate_limit_register_max_requests: int = 5
	rate_limit_email_verify_max_requests: int = 10
	rate_limit_email_verify_resend_max_requests: int = 5
	rate_limit_password_forgot_max_requests: int = 5
	rate_limit_password_reset_max_requests: int = 10
	rate_limit_oauth_max_requests: int = 10
	rate_limit_oauth_window_seconds: int = 900
	rate_limit_notification_read_max_requests: int = 120
	rate_limit_notification_write_max_requests: int = 60
	trusted_proxy_cidrs: Annotated[list[str], NoDecode] = []
	argon2_time_cost: int = 3
	argon2_memory_cost: int = 65536
	argon2_parallelism: int = 4

	# jwt方式
	access_token_ttl_seconds: int = 900
	refresh_ttl_seconds: int = 1209600
	jwt_secret_key: str
	jwt_algorithm: str = "HS256"
	cookie_name_refresh: str = "cerberus_rt"
	cookie_samesite_refresh: Literal["lax", "strict", "none"] = "strict"

	# CORS・API公開設定
	cors_allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
	enable_api_docs: bool = True

	# ページング
	pagination_default_per_page: int = 20
	pagination_max_per_page: int = 100
	task_comment_body_max_length: int = 2000

	# Google OAuth2
	google_login_enabled: bool = True
	google_client_id: str
	google_client_secret: str
	google_redirect_uri: str = "http://localhost:5173/api/auth/oauth/google/callback"
	google_authorize_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
	google_token_endpoint: str = "https://oauth2.googleapis.com/token"
	google_userinfo_endpoint: str = "https://openidconnect.googleapis.com/v1/userinfo"
	google_jwks_uri: str = "https://www.googleapis.com/oauth2/v3/certs"
	google_jwks_cache_ttl_seconds: int = 3600
	google_oauth_prompt: str = "select_account"
	oauth_state_ttl_seconds: int = 600
	oauth_handoff_ttl_seconds: int = 60
	oauth_default_redirect_to: str = "/dashboard"

	# メール（SMTP/Mailpit）
	smtp_host: str = "mailpit"
	smtp_port: int = 1025
	smtp_user: str = ""
	smtp_password: str = ""
	smtp_use_tls: bool = False
	mail_from: str = "no-reply@cerberus.local"
	frontend_base_url: str = "http://localhost:5173"
	password_reset_ttl_seconds: int = 1800
	email_verify_ttl_seconds: int = 86400
	email_verify_resend_interval_seconds: int = 60

	# 初期データ
	initial_admin_email: str
	initial_admin_username: str
	initial_admin_password: str

	# 通知・batch（backendはAPP_TIMEZONEのみ共有参照）
	app_timezone: str = "Asia/Tokyo"

	# 追加項目（§3.12）
	csrf_trust_referer_on_https: bool = False
	health_check_timeout_seconds: float = 2
	login_history_list_limit: int = 50

	@field_validator("cors_allow_origins", "trusted_proxy_cidrs", mode="before")
	@classmethod
	def _split_comma_separated(cls, value: object) -> object:
		if isinstance(value, str):
			return [item.strip() for item in value.split(",") if item.strip()]
		return value

	@field_validator("initial_admin_email", "initial_admin_username", "initial_admin_password")
	@classmethod
	def _reject_blank(cls, value: str) -> str:
		if not value.strip():
			raise ValueError("must not be blank")
		return value

	@field_validator(
		"session_ttl_seconds",
		"session_absolute_ttl_seconds",
		"access_token_ttl_seconds",
		"refresh_ttl_seconds",
		"google_jwks_cache_ttl_seconds",
		"oauth_state_ttl_seconds",
		"oauth_handoff_ttl_seconds",
		"password_reset_ttl_seconds",
		"email_verify_ttl_seconds",
	)
	@classmethod
	def _validate_positive_ttl(cls, value: int) -> int:
		if value <= 0:
			raise ValueError("TTL must be positive")
		return value


@lru_cache
def get_backend_settings() -> BackendSettings:
	return BackendSettings()

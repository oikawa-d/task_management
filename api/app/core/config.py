"""環境変数から読み込むバックエンド設定（`BackendSettings`）を定義するモジュール。"""

from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.constants import (
	AUTH_TOKEN_MAX_LENGTH,
	PASSWORD_MAX_LENGTH,
	PASSWORD_MIN_LENGTH,
	TOKEN_URLSAFE_LENGTH,
)

AuthMode = Literal["session", "jwt"]

_PRODUCTION_PLACEHOLDERS = frozenset({"secret", "password", "changeme", "change-me", "test-secret", "test-password"})


class BackendSettings(BaseSettings):
	"""環境変数（`.env`）から読み込むバックエンドAPIの全設定値。

	`get_backend_settings()`経由でプロセス内シングルトンとして利用する。
	フィールドは用途ごとに以下のセクションへ分類している。

	- 共通・ポート: 実行環境種別、ログレベル
	- データストア: DB/Redis接続、各種履歴の保持日数・サイズ上限
	- 認証共通・session方式: セッションCookie名・TTL、ログイン試行制限、
		各種レート制限の閾値・時間窓、信頼済みプロキシ、argon2idコストパラメータ
	- jwt方式: アクセス/リフレッシュトークンTTL、JWT署名鍵・アルゴリズム
	- CORS・API公開設定: 許可オリジン/メソッド/ヘッダ、APIドキュメント公開可否
	- ページング: 一覧APIの1ページ件数上限、コメント本文長上限
	- Google OAuth2: クライアント資格情報、各エンドポイントURL、state/handoffのTTL
	- メール（SMTP/Mailpit）: 送信設定、パスワードリセット/メール認証のTTL
	- 初期データ: 初回起動時に作成する管理者アカウント
	- 通知・batch: `batch`コンテナと共有するタイムゾーン
	- 追加項目: CSRF・ヘルスチェック・検索等の個別設定

	`app_env="production"`時は`_validate_production_security`で本番相応の
	安全な値になっているかを追加検証する。
	"""

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
	password_max_length: int = PASSWORD_MAX_LENGTH
	auth_token_max_length: int = AUTH_TOKEN_MAX_LENGTH
	login_lock_window_seconds: int = 900
	rate_limit_register_max_requests: int = 5
	rate_limit_register_window_seconds: int = 900
	rate_limit_email_verify_max_requests: int = 10
	rate_limit_email_verify_window_seconds: int = 900
	rate_limit_email_verify_resend_max_requests: int = 5
	rate_limit_email_verify_resend_window_seconds: int = 900
	rate_limit_password_forgot_max_requests: int = 5
	rate_limit_password_forgot_window_seconds: int = 900
	rate_limit_password_reset_max_requests: int = 10
	rate_limit_password_reset_window_seconds: int = 900
	rate_limit_oauth_max_requests: int = 10
	rate_limit_oauth_window_seconds: int = 900
	rate_limit_notification_read_max_requests: int = 120
	rate_limit_notification_write_max_requests: int = 60
	rate_limit_notification_window_seconds: int = 60
	trusted_proxy_cidrs: Annotated[list[str], NoDecode] = []  # X-Forwarded-Forを信頼するプロキシのCIDR一覧
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
	cors_allow_methods: Annotated[list[str], NoDecode] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
	cors_allow_headers: Annotated[list[str], NoDecode] = ["Content-Type", "X-CSRF-Token", "Authorization"]
	cors_max_age_seconds: int = 600
	enable_api_docs: bool = True  # /api/docs（Swagger UI）を公開するか。本番ではfalse必須

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
	oauth_redirect_to_max_length: int = 2048

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
	csrf_trust_referer_on_https: bool = False  # HTTPS時にOriginヘッダ欠落をRefererで代替検証するか
	health_check_timeout_seconds: float = 2  # ヘルスチェックでDB/Redis疎通確認を待つ最大秒数
	login_history_list_limit: int = 50  # ログイン履歴一覧APIの最大取得件数
	admin_search_query_max_length: int = 100  # 管理者検索APIのクエリ文字列最大長

	@field_validator(
		"cors_allow_origins", "cors_allow_methods", "cors_allow_headers", "trusted_proxy_cidrs", mode="before"
	)
	@classmethod
	def _split_comma_separated(cls, value: object) -> object:
		"""環境変数がカンマ区切り文字列の場合にリストへ変換する（`NoDecode`指定フィールド向け前処理）。"""
		if isinstance(value, str):
			return [item.strip() for item in value.split(",") if item.strip()]
		return value

	@field_validator("cors_allow_origins")
	@classmethod
	def _reject_wildcard_origin(cls, value: list[str]) -> list[str]:
		"""`cors_allow_origins`にワイルドカード`"*"`が含まれる場合は設定エラーとする。

		Raises:
			ValueError: `"*"`が含まれる場合。
		"""
		# app.main.appのCORSMiddlewareはallow_credentials=Trueで固定登録しているため、
		# ここでのワイルドカード禁止は常にその前提で成立する（docs/detailed_design/auth/03_csrf.md §10）。
		if "*" in value:
			raise ValueError("cors_allow_origins must not contain '*' when allow_credentials is True")
		return value

	@field_validator("initial_admin_email", "initial_admin_username", "initial_admin_password")
	@classmethod
	def _reject_blank(cls, value: str) -> str:
		"""初期管理者アカウントのメール・ユーザー名・パスワードが空文字でないことを検証する。

		Raises:
			ValueError: 空白のみを含む場合。
		"""
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
		"""各種TTL（有効期限）設定が正の値であることを検証する。

		Raises:
			ValueError: 0以下の値が指定された場合。
		"""
		if value <= 0:
			raise ValueError("TTL must be positive")
		return value

	@field_validator("password_max_length", "auth_token_max_length")
	@classmethod
	def _validate_positive_input_limit(cls, value: int) -> int:
		"""パスワード・トークンの入力長上限が正の値であることを検証する。

		Raises:
			ValueError: 0以下の値が指定された場合。
		"""
		if value <= 0:
			raise ValueError("input length limit must be positive")
		return value

	@field_validator("password_max_length")
	@classmethod
	def _validate_password_maximum(cls, value: int) -> int:
		"""パスワード最大長が最小長（`PASSWORD_MIN_LENGTH`）以上であることを検証する。

		Raises:
			ValueError: `PASSWORD_MIN_LENGTH`未満の値が指定された場合。
		"""
		if value < PASSWORD_MIN_LENGTH:
			raise ValueError(f"password_max_length must be at least {PASSWORD_MIN_LENGTH}")
		return value

	@field_validator("auth_token_max_length")
	@classmethod
	def _validate_auth_token_minimum(cls, value: int) -> int:
		"""認証トークン最大長がトークン生成長（`TOKEN_URLSAFE_LENGTH`）以上であることを検証する。

		Raises:
			ValueError: `TOKEN_URLSAFE_LENGTH`未満の値が指定された場合。
		"""
		if value < TOKEN_URLSAFE_LENGTH:
			raise ValueError(f"auth_token_max_length must be at least {TOKEN_URLSAFE_LENGTH}")
		return value

	@model_validator(mode="after")
	def _validate_production_security(self) -> "BackendSettings":
		"""`app_env="production"`時に、安全でない設定値の組み合わせを起動時に検出する。

		Cookieの`Secure`属性、SMTPのTLS、公開URLのHTTPS化、APIドキュメント非公開、
		秘匿情報（JWT鍵・OAuthクライアントシークレット・初期管理者パスワード）が
		開発用プレースホルダのままでないこと、をまとめて検証する。

		Raises:
			ValueError: いずれかの検証に違反した場合。違反内容を`; `区切りで連結して送出する。
		"""
		if self.app_env != "production":
			return self

		violations: list[str] = []
		if not self.cookie_secure:
			violations.append("cookie_secure must be true in production")
		if not self.smtp_use_tls:
			violations.append("smtp_use_tls must be true in production")
		url_fields = ["frontend_base_url"]
		if self.google_login_enabled:
			url_fields.append("google_redirect_uri")
		for field_name in url_fields:
			parsed = urlparse(getattr(self, field_name))
			if parsed.scheme != "https" or not parsed.netloc:
				violations.append(f"{field_name} must be an HTTPS URL in production")
		if self.enable_api_docs:
			violations.append("enable_api_docs must be false in production")
		for field_name in ("jwt_secret_key", "google_client_secret", "initial_admin_password"):
			value = getattr(self, field_name).strip().lower()
			if not value:
				violations.append(f"{field_name} must not be blank in production")
			elif value in _PRODUCTION_PLACEHOLDERS:
				violations.append(f"{field_name} must not use a development placeholder in production")
		if violations:
			raise ValueError("; ".join(violations))
		return self


@lru_cache
def get_backend_settings() -> BackendSettings:
	"""`BackendSettings`をプロセス内で1度だけ生成し、以降はキャッシュを返す。

	Returns:
		環境変数から読み込んだ設定のシングルトンインスタンス。
	"""
	return BackendSettings()

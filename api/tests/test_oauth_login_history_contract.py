from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CALLBACK_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/api/auth/12_get_auth_oauth_google_callback.md"
EXCHANGE_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/api/auth/13_post_auth_oauth_exchange.md"
LOGIN_HISTORY_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/database/03_table_login_history.md"


def _read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_session_callback_records_verified_user_email() -> None:
	text = _read(CALLBACK_DOCUMENT)

	assert "sessionなら`strategy.login()`＋`login_history(login_identifier=user.email)`記録" in text
	assert "`login_identifier=user.email`が記録される" in text


def test_jwt_exchange_records_verified_user_email() -> None:
	text = _read(EXCHANGE_DOCUMENT)

	assert (
		"async def create(db: AsyncSession, user_id: uuid.UUID | None, login_identifier: str, "
		"login_method: str, ip_address: str | None, user_agent: str | None, success: bool, "
		"failure_reason: str | None) -> None"
	) in text
	assert "`login_identifier=user.email`、`login_method='oauth_google'`を渡す" in text
	assert (
		"`login_history`に`method='oauth_google', login_identifier=user.email, success=true`の行が1件追加される"
	) in text


def test_login_history_lifecycle_separates_oauth_recording_triggers() -> None:
	text = _read(LOGIN_HISTORY_DOCUMENT)

	assert "OAuthではsessionモードはOAuthコールバック成功時" in text
	assert "jwtモードは`/api/auth/oauth/exchange`成功時" in text

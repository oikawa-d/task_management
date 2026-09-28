"""OAuthコールバック・exchangeエンドポイントの詳細設計書と`login_history`テーブル設計書の間で、
ログイン履歴記録の契約（記録タイミング・記録内容・失敗時の非記録）が一致していることを検証するテスト。
"""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CALLBACK_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/api/auth/12_get_auth_oauth_google_callback.md"
EXCHANGE_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/api/auth/13_post_auth_oauth_exchange.md"
LOGIN_HISTORY_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/database/03_table_login_history.md"


def _read(path: Path) -> str:
	"""指定したパスのテキストファイルをUTF-8として読み込むヘルパー関数。

	Returns:
		str: ファイルの全文。
	"""
	return path.read_text(encoding="utf-8")


def test_session_callback_records_verified_user_email() -> None:
	"""OAuthコールバック設計書に、sessionモード成功時は`strategy.login()`と併せて
	`login_identifier=user.email`で`login_history`へ記録する旨の記載があることを検証する。
	"""
	text = _read(CALLBACK_DOCUMENT)

	assert "sessionなら`strategy.login()`＋`login_history(login_identifier=user.email)`記録" in text
	assert "`login_identifier=user.email`が記録される" in text


def test_jwt_exchange_records_verified_user_email() -> None:
	"""OAuth exchangeエンドポイント設計書に、`login_history`作成関数のシグネチャと、
	`login_identifier=user.email`・`login_method='oauth_google'`を渡して成功行を1件追加する旨の
	記載があることを検証する。
	"""
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
	"""`login_history`テーブル設計書に、OAuthのsessionモードはコールバック成功時、
	jwtモードは`/api/auth/oauth/exchange`成功時にそれぞれ記録される、という
	モード別の記録契機の記載があることを検証する。
	"""
	text = _read(LOGIN_HISTORY_DOCUMENT)

	assert "OAuthではsessionモードはOAuthコールバック成功時" in text
	assert "jwtモードは`/api/auth/oauth/exchange`成功時" in text


def test_oauth_callback_failures_are_not_recorded_in_login_history() -> None:
	"""OAuthコールバック設計書に、`oauth_denied`・`oauth_failed`・`oauth_email_unverified`等の
	コールバック失敗時は`login_history`へ記録しない旨の記載があることを検証する。
	"""
	text = _read(CALLBACK_DOCUMENT)

	assert (
		"OAuth callback失敗（`oauth_denied`、`oauth_failed`、`oauth_email_unverified`等）は`login_history`へ記録しない"
	) in text

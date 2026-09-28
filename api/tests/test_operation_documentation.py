"""運用設計書（`07_operation.md`）のリンク切れ有無、運用手順書として必要な項目の網羅、
および環境変数設計書（`04_env_config.md`）との設定項目名の整合性を検証するテスト。
"""

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OPERATION_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/infra/07_operation.md"
ENVIRONMENT_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/infra/04_env_config.md"
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")


def _read_document(path: Path) -> str:
	"""指定した設計書ファイルの全文をUTF-8で読み込むヘルパー関数。

	Returns:
		str: ファイルの全文。
	"""
	return path.read_text(encoding="utf-8")


def test_operation_document_local_links_resolve() -> None:
	"""運用設計書中のMarkdownリンク（外部URL・mailto:を除く）が指すローカルファイルが、
	すべて実際に存在することを検証する。
	"""
	text = _read_document(OPERATION_DOCUMENT)
	missing_links: list[str] = []

	for target in MARKDOWN_LINK_PATTERN.findall(text):
		if target.startswith(("http://", "https://", "mailto:")):
			continue
		resolved = (OPERATION_DOCUMENT.parent / target).resolve()
		if not resolved.is_file():
			missing_links.append(target)

	assert missing_links == []


def test_operation_document_contains_verifiable_runbook_items() -> None:
	"""運用設計書に、ヘルスチェックエンドポイント・ログ確認コマンド・バックアップ/リストアコマンド・
	保存期間パージ用SP・Redis再起動手順・`AUTH_MODE`・テスト設計節・不明点節・
	自動スケジューリングをスコープ外とする記載など、運用手順として検証可能な項目が
	一通り含まれていることを検証する。
	"""
	text = _read_document(OPERATION_DOCUMENT)
	required_items = (
		"GET /api/health",
		"docker compose logs",
		"pg_dump",
		"psql",
		"sp_purge_login_history",
		"docker compose restart redis",
		"AUTH_MODE",
		"## 11. テスト設計",
		"## 12. 不明点・要検討事項",
		"自動スケジューリング（cron等）は要件書§11のスコープ外",
	)

	missing_items = [item for item in required_items if item not in text]

	assert missing_items == []


def test_operation_document_settings_are_defined_in_environment_document() -> None:
	"""ログレベルや各種履歴保存期間・認証モード・DockerCompose関連の設定項目名が、
	運用設計書と環境変数設計書の両方にバッククォート付きで記載されていることを検証する。
	"""
	operation_text = _read_document(OPERATION_DOCUMENT)
	environment_text = _read_document(ENVIRONMENT_DOCUMENT)
	settings = (
		"LOG_LEVEL",
		"LOGIN_HISTORY_RETENTION_DAYS",
		"API_HISTORY_RETENTION_DAYS",
		"BATCH_HISTORY_RETENTION_DAYS",
		"AUTH_MODE",
		"POSTGRES_USER",
		"POSTGRES_DB",
		"COMPOSE_PROJECT_NAME",
		"HEALTH_CHECK_TIMEOUT_SECONDS",
	)

	missing_from_operation = [name for name in settings if f"`{name}`" not in operation_text]
	missing_from_environment = [name for name in settings if f"`{name}`" not in environment_text]

	assert missing_from_operation == []
	assert missing_from_environment == []

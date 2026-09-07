import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OPERATION_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/infra/07_operation.md"
ENVIRONMENT_DOCUMENT = REPOSITORY_ROOT / "docs/detailed_design/infra/04_env_config.md"
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")


def _read_document(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_operation_document_local_links_resolve() -> None:
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

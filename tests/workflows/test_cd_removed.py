"""開発・学習用途ではCDを配置しないことを検証する。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEV_COMPOSE_COMMAND = "docker compose -f docker-compose.yml -f compose.dev.yml --profile dev"
DEV_COMPOSE_DOCS = (
	ROOT / "docs/requirements/task_management_requirements.md",
	ROOT / "docs/basic_design/06_infra_cicd.md",
	ROOT / "docs/detailed_design/infra/01_docker_compose.md",
	ROOT / "docs/detailed_design/infra/06_cd_workflow.md",
)
DEV_COMPOSE_START_DOCS = (ROOT / "AGENTS.md",)


def _env_example_keys() -> set[str]:
	return {
		line.split("=", 1)[0]
		for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
		if line and not line.startswith("#") and "=" in line
	}


def test_only_ci_workflow_exists_and_contains_no_deploy_features() -> None:
	workflow_dir = ROOT / ".github/workflows"
	workflow_files = {
		path.relative_to(workflow_dir)
		for path in workflow_dir.rglob("*")
		if path.is_file() and path.suffix in {".yml", ".yaml"}
	}

	assert workflow_files == {Path("ci.yml")}
	assert not (ROOT / ".github/actionlint.yaml").exists()

	for workflow_file in workflow_files:
		content = (workflow_dir / workflow_file).read_text(encoding="utf-8")
		content_lower = content.lower()
		assert "self-hosted" not in content_lower
		assert "docker/login-action" not in content_lower
		assert "ghcr.io" not in content_lower
		assert re.search(r"environment\s*:\s*production", content_lower) is None
		assert re.search(r"push\s*:\s*true", content_lower) is None


def test_env_example_does_not_contain_cd_only_settings() -> None:
	env_keys = _env_example_keys()

	assert "IMAGE_RETENTION_DAYS" not in env_keys
	assert not any(key.startswith("DEPLOY_") for key in env_keys)


def test_local_compose_commands_enable_mailpit_profile() -> None:
	compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

	assert "mailpit:" in compose
	assert "profiles: [dev]" in compose
	for document in DEV_COMPOSE_DOCS:
		content = document.read_text(encoding="utf-8")
		assert f"{DEV_COMPOSE_COMMAND} up" in content
		assert f"{DEV_COMPOSE_COMMAND} down" in content
	for document in DEV_COMPOSE_START_DOCS:
		content = document.read_text(encoding="utf-8")
		assert f"{DEV_COMPOSE_COMMAND} up" in content

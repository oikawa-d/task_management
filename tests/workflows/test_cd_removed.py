"""開発・学習用途ではCDを配置しないことを検証する。"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _env_example_keys() -> set[str]:
	return {
		line.split("=", 1)[0]
		for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
		if line and not line.startswith("#") and "=" in line
	}


def test_cd_workflow_and_actionlint_config_are_absent() -> None:
	assert not (ROOT / ".github/workflows/cd.yml").exists()
	assert not (ROOT / ".github/actionlint.yaml").exists()


def test_env_example_does_not_contain_cd_only_settings() -> None:
	cd_only_keys = {"DEPLOY_STATE_FILE", "IMAGE_RETENTION_DAYS"}

	assert cd_only_keys.isdisjoint(_env_example_keys())

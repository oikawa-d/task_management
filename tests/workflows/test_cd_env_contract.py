"""CDの環境変数・frontend build-argが実装と雛形から漏れないことを検証する。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CD_WORKFLOW_PATH = ROOT / ".github/workflows/cd.yml"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
FRONTEND_DOCKERFILE_PATH = ROOT / "frontend/Dockerfile"

DEV_ONLY_KEYS = {"MAILPIT_SMTP_PORT", "MAILPIT_UI_PORT", "REDIS_TEST_DB"}
WORKFLOW_ONLY_KEYS = {"DEPLOY_STATE_FILE", "IMAGE_RETENTION_DAYS"}


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
	return yaml.safe_load(CD_WORKFLOW_PATH.read_text(encoding="utf-8"))


def _env_example_keys() -> set[str]:
	return {
		line.split("=", 1)[0]
		for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
		if line and not line.startswith("#") and "=" in line
	}


def _env_generation_run(workflow: dict[str, Any]) -> str:
	steps = workflow["jobs"]["deploy"]["steps"]
	return next(step["run"] for step in steps if "cat <<EOF > .env" in step.get("run", ""))


def _env_generation_keys(workflow: dict[str, Any]) -> set[str]:
	return set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)=", _env_generation_run(workflow), re.MULTILINE))


def _frontend_build_step(workflow: dict[str, Any]) -> dict[str, Any]:
	steps = workflow["jobs"]["build-and-push"]["steps"]
	return next(
		step
		for step in steps
		if step.get("uses", "").startswith("docker/build-push-action")
		and step.get("with", {}).get("context") == "frontend"
	)


def _frontend_dockerfile_args() -> set[str]:
	return set(
		re.findall(
			r"^\s*ARG\s+(VITE_[A-Z0-9_]+)(?:=|\s|$)",
			FRONTEND_DOCKERFILE_PATH.read_text(encoding="utf-8"),
			re.MULTILINE,
		)
	)


def _build_arg_names(step: dict[str, Any]) -> set[str]:
	return set(re.findall(r"^\s*(VITE_[A-Z0-9_]+)=", step["with"]["build-args"], re.MULTILINE))


def test_cd_env_generation_covers_production_env_example(workflow: dict[str, Any]) -> None:
	frontend_build_only = _frontend_dockerfile_args() - {"VITE_API_BASE_URL"}
	expected = _env_example_keys() - DEV_ONLY_KEYS - WORKFLOW_ONLY_KEYS - frontend_build_only

	assert expected <= _env_generation_keys(workflow)


def test_cd_frontend_build_passes_every_dockerfile_arg(workflow: dict[str, Any]) -> None:
	build_args = _build_arg_names(_frontend_build_step(workflow))

	assert _frontend_dockerfile_args() <= build_args


def test_cd_keeps_deploy_state_settings_in_job_environment(workflow: dict[str, Any]) -> None:
	job_env = workflow["jobs"]["deploy"]["env"]

	assert WORKFLOW_ONLY_KEYS <= job_env.keys()
	assert WORKFLOW_ONLY_KEYS.isdisjoint(_env_generation_keys(workflow))

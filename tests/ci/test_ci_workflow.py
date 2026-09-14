"""infra/05_ci_workflow.mdの設計と.github/workflows/ci.ymlの実装が一致していることを検証する。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github/workflows/ci.yml"
API_REQUIREMENTS_DEV_PATH = ROOT / "api/requirements-dev.txt"


def _load_workflow() -> dict[Any, Any]:
	with WORKFLOW_PATH.open(encoding="utf-8") as f:
		# YAML上の"on:"キーはPyYAMLがブール値Trueとして解釈するため、後段の
		# トリガー検証では文字列/真偽値どちらのキーでも参照できるようにする。
		return cast(dict[Any, Any], yaml.safe_load(f))


def test_workflow_file_exists() -> None:
	assert WORKFLOW_PATH.is_file()


def test_triggers_are_push_and_pull_request_on_main_and_develop() -> None:
	workflow = _load_workflow()
	triggers = workflow.get("on") or workflow.get(True)
	assert triggers is not None
	for event in ("push", "pull_request"):
		assert set(triggers[event]["branches"]) == {"main", "develop"}


def test_required_jobs_are_defined() -> None:
	jobs = _load_workflow()["jobs"]
	required = {
		"backend-lint",
		"backend-test",
		"frontend-lint",
		"frontend-test",
		"batch-test",
		"batch-container-integration",
		"docker-build",
		"hook-test",
	}
	assert required.issubset(jobs.keys())


def test_backend_test_uses_auth_mode_matrix() -> None:
	backend_test = _load_workflow()["jobs"]["backend-test"]
	assert backend_test["strategy"]["matrix"]["auth_mode"] == ["session", "jwt"]
	assert backend_test["env"]["AUTH_MODE"] == "${{ matrix.auth_mode }}"


def test_backend_test_enforces_coverage_threshold() -> None:
	steps = _load_workflow()["jobs"]["backend-test"]["steps"]
	pytest_step = next(step for step in steps if "pytest --cov" in step.get("run", ""))
	assert "--cov-fail-under=80" in pytest_step["run"]


def test_docker_build_requires_all_quality_jobs_and_never_pushes() -> None:
	docker_build = _load_workflow()["jobs"]["docker-build"]
	assert set(docker_build["needs"]) == {
		"detect",
		"backend-lint",
		"backend-test",
		"frontend-lint",
		"frontend-test",
		"batch-test",
	}
	build_steps = [
		step for step in docker_build["steps"] if step.get("uses", "").startswith("docker/build-push-action")
	]
	assert len(build_steps) == 3
	for step in build_steps:
		assert step["with"]["push"] is False


def _install_step_run(job_name: str) -> str:
	steps = _load_workflow()["jobs"][job_name]["steps"]
	install_step = next(step for step in steps if "pip install" in step.get("run", ""))
	return cast(str, install_step["run"])


def test_backend_jobs_install_dev_requirements() -> None:
	# 開発用依存（httpx2等）の入れ忘れでpytestのcollectが失敗する事故を防ぐ。
	for job_name in ("backend-lint", "backend-test"):
		run = _install_step_run(job_name)
		assert "-r requirements.txt" in run
		assert "-r requirements-dev.txt" in run


def test_api_dev_requirements_cover_lint_and_test_tools() -> None:
	packages = {
		line.split("==")[0].strip()
		for line in API_REQUIREMENTS_DEV_PATH.read_text(encoding="utf-8").splitlines()
		if line.strip() and not line.startswith("#")
	}
	# httpx2はfastapi.testclient（starlette.testclient）の実行に必須。
	assert {"ruff", "mypy", "pytest", "pytest-cov", "pytest-asyncio", "httpx2"} <= packages


def test_hook_test_runs_all_hook_tests() -> None:
	job = _load_workflow()["jobs"]["hook-test"]
	runs = [step.get("run", "") for step in job["steps"]]
	hook_run = next(run for run in runs if ".claude/hooks/*.test.sh" in run)
	assert 'bash "$test_file"' in hook_run

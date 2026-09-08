"""infra/05_ci_workflow.mdの設計と.github/workflows/ci.ymlの実装が一致していることを検証する。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github/workflows/ci.yml"


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

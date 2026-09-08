"""cd.yml（CDワークフロー）の静的構造を検証する。

self-hosted runner実機・GHCR・GitHub Environmentへの実デプロイはCIで自動実行できないため、
docs/detailed_design/infra/06_cd_workflow.md §11 の設計内容がYAML構造として
正しく表現されているかを検証する（実機依存部分は対象外）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CD_WORKFLOW_PATH = ROOT / ".github/workflows/cd.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
	with CD_WORKFLOW_PATH.open(encoding="utf-8") as f:
		# YAMLの`on`キーはPyYAMLがbool Trueとして解釈するため、
		# safe_loadの結果からは`True`キーとして取得する。
		return yaml.safe_load(f)


def _on(workflow: dict[str, Any]) -> dict[str, Any]:
	return workflow.get("on") or workflow.get(True)


def _job_steps(workflow: dict[str, Any], job: str) -> list[dict[str, Any]]:
	return workflow["jobs"][job]["steps"]


def test_cd_triggers_on_main_push_and_manual_dispatch(workflow: dict[str, Any]) -> None:
	on = _on(workflow)
	assert on["push"]["branches"] == ["main"]
	assert "workflow_dispatch" in on


def test_cd_concurrency_group_serializes_deploys(workflow: dict[str, Any]) -> None:
	concurrency = workflow["concurrency"]
	assert concurrency["group"] == "deploy-main"
	assert concurrency["cancel-in-progress"] is False


def test_cd_build_and_push_runs_on_github_hosted_runner(workflow: dict[str, Any]) -> None:
	job = workflow["jobs"]["build-and-push"]
	assert job["runs-on"] == "ubuntu-latest"
	assert job["permissions"]["packages"] == "write"


@pytest.mark.parametrize("component", ("backend", "frontend", "batch"))
def test_cd_build_and_push_creates_both_tags(workflow: dict[str, Any], component: str) -> None:
	steps = _job_steps(workflow, "build-and-push")
	build_step = next(
		s
		for s in steps
		if s.get("uses", "").startswith("docker/build-push-action") and f"cerberus-{component}" in s["with"]["tags"]
	)
	tags = build_step["with"]["tags"]
	assert f"cerberus-{component}:latest" in tags
	assert f"cerberus-{component}:" + "${{ steps.vars.outputs.image_tag }}" in tags
	assert build_step["with"]["push"] is True
	assert f"com.cerberus.component={component}" in build_step["with"]["labels"]
	assert "com.cerberus.managed=true" in build_step["with"]["labels"]


def test_cd_deploy_needs_build_and_push_and_uses_production_environment(workflow: dict[str, Any]) -> None:
	job = workflow["jobs"]["deploy"]
	assert job["needs"] == "build-and-push"
	assert job["environment"] == "production"
	assert job["runs-on"] == ["self-hosted", "linux", "cerberus"]


def test_cd_env_generation_no_secret_leak_in_log(workflow: dict[str, Any]) -> None:
	steps = _job_steps(workflow, "deploy")
	for step in steps:
		run = step.get("run", "")
		if ".env" in run and "cat <<EOF" in run:
			# .env生成ステップ自体はheredocでSecretsを書き込むが、
			# 生成後の内容をログへ出力するcat/echoは存在しないこと
			lines_after_heredoc = run.split("EOF")[-1]
			assert "cat .env" not in run
			assert "echo" not in lines_after_heredoc or ".env" not in lines_after_heredoc


def test_cd_deploy_rollback_on_healthcheck_failure(workflow: dict[str, Any]) -> None:
	steps = _job_steps(workflow, "deploy")
	rollback_step = next(s for s in steps if "ロールバック" in s.get("name", ""))
	assert rollback_step["if"] == "failure() && steps.healthcheck.outcome == 'failure'"
	assert "BACKEND_IMAGE_TAG" in rollback_step["run"]
	assert "FRONTEND_IMAGE_TAG" in rollback_step["run"]
	assert "BATCH_IMAGE_TAG" in rollback_step["run"]
	# 初回デプロイ（直前成功タグなし）はロールバックせずfailureで終了する
	assert "steps.prev.outputs.exists" in rollback_step["run"]


def test_cd_prune_only_managed_images(workflow: dict[str, Any]) -> None:
	steps = _job_steps(workflow, "deploy")
	prune_step = next(s for s in steps if "prune" in s.get("name", ""))
	assert "com.cerberus.managed=true" in prune_step["run"]
	# 稼働中コンテナが使用中のイメージは除外する
	assert "docker ps -a" in prune_step["run"]

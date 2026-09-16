import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INTEGRATION_COMPOSE_FILE = REPOSITORY_ROOT / "compose.integration.yml"
PROBE_FILE = Path(__file__).with_name("probe.py")

pytestmark = [
	pytest.mark.integration,
	pytest.mark.skipif(
		os.getenv("RUN_BATCH_CONTAINER_INTEGRATION") != "1",
		reason="Docker Composeを使う受け入れテストは明示実行時のみ実施します",
	),
]


def _compose_environment() -> dict[str, str]:
	env = os.environ.copy()
	env["COMPOSE_PROJECT_NAME"] = f"batch-connectivity-{os.getpid()}"
	return env


def _run_compose(*arguments: str) -> None:
	command = [
		"docker",
		"compose",
		"--project-directory",
		str(REPOSITORY_ROOT),
		"--project-name",
		_compose_environment()["COMPOSE_PROJECT_NAME"],
		"-f",
		str(INTEGRATION_COMPOSE_FILE),
		*arguments,
	]
	subprocess.run(command, check=True, env=_compose_environment())


@pytest.fixture
def data_stores() -> Iterator[None]:
	try:
		_run_compose("up", "-d", "postgres", "redis")
		yield
	finally:
		_run_compose("down", "--remove-orphans")


def test_batch_container_connects_to_postgres_and_redis(data_stores: None) -> None:
	_run_compose(
		"run",
		"--rm",
		"--no-deps",
		"--build",
		"-v",
		f"{PROBE_FILE}:/app/batch-connectivity-probe.py:ro",
		"batch",
		"python",
		"/app/batch-connectivity-probe.py",
	)

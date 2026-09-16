"""Dockerfileのビルドとランタイム契約を検証する。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]

DOCKERFILES = {
	"api": ROOT / "api/Dockerfile",
	"frontend": ROOT / "frontend/Dockerfile",
	"batch": ROOT / "batch/Dockerfile",
}


def run_docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		["docker", *args],
		cwd=ROOT,
		check=check,
		text=True,
		capture_output=True,
	)


@pytest.mark.parametrize(
	("name", "required_lines"),
	[
		(
			"api",
			(
				"FROM python:3.14-slim AS builder",
				"COPY api/requirements.txt ./requirements.txt",
				"COPY --from=builder /install /usr/local",
				"COPY --chown=appuser:appuser db /app/db",
				"USER appuser",
				'ENTRYPOINT ["./entrypoint.sh"]',
			),
		),
		(
			"frontend",
			(
				"FROM node:26-alpine AS builder",
				"ARG VITE_API_BASE_URL=/api",
				"RUN npm ci",
				"RUN npm run build",
				"FROM nginx:alpine AS runtime",
			),
		),
		(
			"batch",
			(
				"FROM python:3.14-slim AS builder",
				"COPY batch/requirements.txt ./requirements.txt",
				"COPY --from=builder /install /usr/local",
				"USER appuser",
				'CMD ["python", "-m", "app.main"]',
			),
		),
	],
)
def test_dockerfiles_match_design_contract(name: str, required_lines: tuple[str, ...]) -> None:
	contents = DOCKERFILES[name].read_text()

	for line in required_lines:
		assert line in contents


@pytest.fixture(scope="session")
def docker_available() -> None:
	if shutil.which("docker") is None:
		pytest.skip("dockerコマンドがありません")

	try:
		run_docker("info")
	except subprocess.CalledProcessError as exc:
		pytest.skip(f"Docker daemonを利用できません: {exc.stderr.strip()}")


def build_image(name: str) -> tuple[str, bool]:
	tag = os.getenv(f"DOCKER_TEST_IMAGE_{name.upper()}")
	if tag:
		return tag, False

	tag = f"cerberus-test-{name}"
	context = "frontend" if name == "frontend" else "."
	run_docker("build", "--tag", tag, "--file", str(DOCKERFILES[name]), context)
	return tag, True


def inspect_image(tag: str) -> dict[str, Any]:
	result = run_docker("image", "inspect", tag)
	return cast(dict[str, Any], json.loads(result.stdout)[0])


@pytest.mark.parametrize("name", ("api", "frontend", "batch"))
def test_docker_images_build_and_match_runtime_contract(name: str, docker_available: None) -> None:
	tag, should_remove = build_image(name)
	try:
		config = inspect_image(tag)["Config"]
		exposed_ports = config.get("ExposedPorts", {})

		if name == "api":
			assert config["User"] == "appuser"
			assert config["Entrypoint"] == ["./entrypoint.sh"]
			assert "8000/tcp" in exposed_ports
			assert run_docker("run", "--rm", "--entrypoint", "id", tag, "-u").stdout.strip() != "0"
		elif name == "frontend":
			assert "80/tcp" in exposed_ports
			assert config.get("Healthcheck")
			run_docker(
				"run",
				"--rm",
				"--add-host",
				"backend:127.0.0.1",
				"--entrypoint",
				"nginx",
				tag,
				"-t",
			)
		else:
			assert config["User"] == "appuser"
			assert config["Cmd"] == ["python", "-m", "app.main"]
			assert not exposed_ports
			assert run_docker("run", "--rm", "--entrypoint", "id", tag, "-u").stdout.strip() != "0"
	finally:
		if should_remove:
			run_docker("image", "rm", "--force", tag, check=False)

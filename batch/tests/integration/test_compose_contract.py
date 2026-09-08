from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPOSITORY_ROOT / "docker-compose.yml"


def _service_block(service_name: str) -> str:
	lines = COMPOSE_FILE.read_text(encoding="utf-8").splitlines()
	service_start = lines.index(f"  {service_name}:")
	service_lines: list[str] = []
	for line in lines[service_start:]:
		if service_lines and line.startswith("  ") and not line.startswith("    "):
			break
		service_lines.append(line)
	return "\n".join(service_lines)


def test_batch_service_contract_allows_direct_database_and_redis_access() -> None:
	batch_service = _service_block("batch")

	assert "dockerfile: batch/Dockerfile" in batch_service
	assert "env_file:\n      - .env" in batch_service
	assert "postgres:\n        condition: service_healthy" in batch_service
	assert "redis:\n        condition: service_healthy" in batch_service
	assert "networks:\n      - cerberus_net" in batch_service
	assert "ports:" not in batch_service

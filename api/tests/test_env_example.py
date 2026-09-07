import re
from pathlib import Path

from app.core.config import BackendSettings

_REQUIRED_MARKER = "なし（必須）"
_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
_ENV_CONFIG_DESIGN = Path(__file__).resolve().parents[2] / "docs" / "detailed_design" / "infra" / "04_env_config.md"


def _keys_from_env_example() -> set[str]:
	return {
		line.split("=", 1)[0]
		for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
		if line and not line.startswith("#") and "=" in line
	}


def _required_keys_from_design() -> set[str]:
	return {
		match.group(1)
		for line in _ENV_CONFIG_DESIGN.read_text(encoding="utf-8").splitlines()
		if _REQUIRED_MARKER in line
		for match in re.finditer(r"`([A-Z][A-Z0-9_]*)`", line)
	}


def test_env_example_contains_all_design_required_variables() -> None:
	required_keys = _required_keys_from_design()

	assert required_keys <= _keys_from_env_example()


def test_backend_required_variables_are_listed_as_required_in_design() -> None:
	design_required_keys = _required_keys_from_design()
	backend_required_keys = {
		field_name.upper() for field_name, field in BackendSettings.model_fields.items() if field.is_required()
	}

	assert backend_required_keys <= design_required_keys

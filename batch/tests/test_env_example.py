from pathlib import Path

from app.core.config import BatchSettings

_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _keys_from_env_example() -> set[str]:
	return {
		line.split("=", 1)[0]
		for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
		if line and not line.startswith("#") and "=" in line
	}


def test_batch_required_variables_are_listed_in_env_example() -> None:
	required_keys = {
		field_name.upper() for field_name, field in BatchSettings.model_fields.items() if field.is_required()
	}

	assert required_keys <= _keys_from_env_example()

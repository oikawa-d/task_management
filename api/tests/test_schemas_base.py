import pytest
from app.schemas.base import StrictSchema
from pydantic import ValidationError


class _Sample(StrictSchema):
	name: str


def test_strict_schema_accepts_defined_field() -> None:
	assert _Sample(name="taro").name == "taro"


def test_strict_schema_rejects_undefined_field() -> None:
	with pytest.raises(ValidationError):
		_Sample(name="taro", unexpected="value")


def test_strict_schema_config_forbids_extra() -> None:
	assert StrictSchema.model_config.get("extra") == "forbid"

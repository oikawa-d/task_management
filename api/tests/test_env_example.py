"""`.env.example`・`docs/detailed_design/infra/04_env_config.md`・`BackendSettings`の
必須環境変数の一覧が相互に整合していることを検証するテスト。
"""

import re
from pathlib import Path

from app.core.config import BackendSettings

_REQUIRED_MARKER = "なし（必須）"
_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
_ENV_CONFIG_DESIGN = Path(__file__).resolve().parents[2] / "docs" / "detailed_design" / "infra" / "04_env_config.md"


def _keys_from_env_example() -> set[str]:
	"""`.env.example`からコメント・空行を除いた各行のキー名（`=`より前）を集合として抽出するヘルパー関数。

	Returns:
		set[str]: `.env.example`に定義されている環境変数キー名の集合。
	"""
	return {
		line.split("=", 1)[0]
		for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
		if line and not line.startswith("#") and "=" in line
	}


def _required_keys_from_design() -> set[str]:
	"""環境変数設計書のうち`_REQUIRED_MARKER`（「なし（必須）」）を含む行から、
	バッククォートで囲まれた大文字始まりの識別子を必須環境変数キーとして抽出するヘルパー関数。

	Returns:
		set[str]: 設計書上で必須と記載されている環境変数キー名の集合。
	"""
	return {
		match.group(1)
		for line in _ENV_CONFIG_DESIGN.read_text(encoding="utf-8").splitlines()
		if _REQUIRED_MARKER in line
		for match in re.finditer(r"`([A-Z][A-Z0-9_]*)`", line)
	}


def test_env_example_contains_all_design_required_variables() -> None:
	"""設計書が必須と定める環境変数キーが、すべて`.env.example`にも定義されていることを検証する。"""
	required_keys = _required_keys_from_design()

	assert required_keys <= _keys_from_env_example()


def test_backend_required_variables_are_listed_as_required_in_design() -> None:
	"""`BackendSettings`でデフォルト値が無い（必須の）フィールド名を大文字化したキーが、
	すべて設計書上の必須環境変数キーに含まれていることを検証する。
	"""
	design_required_keys = _required_keys_from_design()
	backend_required_keys = {
		field_name.upper() for field_name, field in BackendSettings.model_fields.items() if field.is_required()
	}

	assert backend_required_keys <= design_required_keys

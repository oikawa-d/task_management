"""
ベーススキーマ StrictSchema のバリデーション（extra="forbid"）を検証するテスト。
"""

import pytest
from app.schemas.base import StrictSchema
from pydantic import ValidationError


class _Sample(StrictSchema):
	"""
	StrictSchema の動作を検証するためのサンプルスキーマ。

	Attributes:
		name: 文字列フィールド。
	"""

	name: str


def test_strict_schema_accepts_defined_field() -> None:
	"""
	StrictSchema が定義済みフィールドを受け入れることを検証。

	条件：定義済みフィールド name に有効な値を入力したとき、フィールドが正しく保持されること。
	"""
	assert _Sample(name="taro").name == "taro"


def test_strict_schema_rejects_undefined_field() -> None:
	"""
	StrictSchema が予期しないフィールド（extra="forbid"）を拒否することを検証。

	条件：定義済みフィールド name に加えて、未定義フィールド unexpected を入力したとき、ValidationError が送出されること。
	"""
	with pytest.raises(ValidationError):
		_Sample(name="taro", unexpected="value")


def test_strict_schema_config_forbids_extra() -> None:
	"""
	StrictSchema の model_config が extra="forbid" に設定されていることを検証。

	条件：StrictSchema.model_config.get("extra") が "forbid" の値を返すこと。
	"""
	assert StrictSchema.model_config.get("extra") == "forbid"

"""pydanticスキーマから利用する、設定値ベースの入力長バリデーション関数を提供するモジュール。"""

from app.core.config import get_backend_settings


def validate_password_max_length(value: str) -> str:
	"""パスワード文字列が設定上の最大長（`password_max_length`）以内であることを検証する。

	Args:
		value: 検証対象のパスワード文字列。

	Returns:
		検証をパスした場合はそのまま`value`。

	Raises:
		ValueError: 最大長を超える場合（pydanticのフィールドバリデータとして使用される）。
	"""
	max_length = get_backend_settings().password_max_length
	if len(value) > max_length:
		raise ValueError(f"password must be at most {max_length} characters")
	return value


def validate_auth_token_max_length(value: str) -> str:
	"""認証トークン/コード文字列が設定上の最大長（`auth_token_max_length`）以内であることを検証する。

	Args:
		value: 検証対象のトークンまたは認証コード文字列。

	Returns:
		検証をパスした場合はそのまま`value`。

	Raises:
		ValueError: 最大長を超える場合（pydanticのフィールドバリデータとして使用される）。
	"""
	max_length = get_backend_settings().auth_token_max_length
	if len(value) > max_length:
		raise ValueError(f"token or code must be at most {max_length} characters")
	return value

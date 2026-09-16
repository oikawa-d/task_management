from app.core.config import get_backend_settings


def validate_password_max_length(value: str) -> str:
	max_length = get_backend_settings().password_max_length
	if len(value) > max_length:
		raise ValueError(f"password must be at most {max_length} characters")
	return value


def validate_auth_token_max_length(value: str) -> str:
	max_length = get_backend_settings().auth_token_max_length
	if len(value) > max_length:
		raise ValueError(f"token or code must be at most {max_length} characters")
	return value

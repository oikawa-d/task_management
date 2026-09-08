from typing import Any, cast

import jwt
from jwt import InvalidTokenError as JwtDecodeError


def encode_jwt(claims: dict[str, Any], secret_key: str, algorithm: str) -> str:
	return jwt.encode(claims, secret_key, algorithm=algorithm)


def decode_jwt(token: str, secret_key: str, algorithm: str) -> dict[str, Any]:
	return cast(
		dict[str, Any],
		jwt.decode(
			token,
			secret_key,
			algorithms=[algorithm],
			options={"require": ["sub", "iat", "exp", "jti", "typ"]},
		),
	)


__all__ = ["JwtDecodeError", "decode_jwt", "encode_jwt"]

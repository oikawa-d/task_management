from functools import lru_cache
from typing import Any, cast

import jwt
from jwt import InvalidTokenError as JwtDecodeError
from passlib.context import CryptContext

from app.core.config import get_backend_settings


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


def _build_password_context() -> CryptContext:
	settings = get_backend_settings()
	return CryptContext(
		schemes=["argon2"],
		argon2__time_cost=settings.argon2_time_cost,
		argon2__memory_cost=settings.argon2_memory_cost,
		argon2__parallelism=settings.argon2_parallelism,
	)


def hash_password(plain_password: str) -> str:
	"""argon2idでパスワードをハッシュ化する。"""
	return _build_password_context().hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
	"""平文パスワードとハッシュを照合する。不正な形式のハッシュはFalseを返す。"""
	try:
		return _build_password_context().verify(plain_password, password_hash)
	except ValueError:
		return False


def needs_rehash(password_hash: str) -> bool:
	"""現在のargon2idコストパラメータと異なる場合にTrueを返す。"""
	return _build_password_context().needs_update(password_hash)


_DUMMY_PASSWORD = "dummy-password-for-timing-attack-mitigation"


@lru_cache(maxsize=1)
def get_dummy_password_hash() -> str:
	"""ユーザー不存在時にも同じ検証コストを支払うためのダミーハッシュ（タイミング攻撃対策）。"""
	return hash_password(_DUMMY_PASSWORD)


__all__ = [
	"JwtDecodeError",
	"decode_jwt",
	"encode_jwt",
	"get_dummy_password_hash",
	"hash_password",
	"needs_rehash",
	"verify_password",
]

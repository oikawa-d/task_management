"""JWT署名・パスワードハッシュ化・CSRFトークン比較など、暗号関連の共通処理を提供するモジュール。"""

import secrets
from functools import lru_cache
from typing import Any, cast

import jwt
from jwt import InvalidTokenError as JwtDecodeError
from passlib.context import CryptContext

from app.core.config import get_backend_settings


def encode_jwt(claims: dict[str, Any], secret_key: str, algorithm: str) -> str:
	"""クレーム（ペイロード）を指定の鍵・アルゴリズムで署名し、JWT文字列を生成する。

	Args:
		claims: JWTに含めるクレーム（`sub`/`iat`/`exp`/`jti`/`typ`等）。
		secret_key: 署名に使う秘密鍵。
		algorithm: 署名アルゴリズム（例: "HS256"）。

	Returns:
		署名済みのJWT文字列。
	"""
	return jwt.encode(claims, secret_key, algorithm=algorithm)


def decode_jwt(token: str, secret_key: str, algorithm: str) -> dict[str, Any]:
	"""JWTを検証・デコードし、クレームを返す。

	`sub`/`iat`/`exp`/`jti`/`typ`の各クレームが必須であることも合わせて検証する。

	Args:
		token: デコード対象のJWT文字列。
		secret_key: 署名検証に使う秘密鍵。
		algorithm: 署名アルゴリズム（例: "HS256"）。

	Returns:
		デコードされたクレーム。

	Raises:
		JwtDecodeError: 署名不正・有効期限切れ・必須クレーム欠落など、検証に失敗した場合。
	"""
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
	"""設定値（argon2コストパラメータ）を反映したargon2id用の`CryptContext`を生成する。"""
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


def csrf_tokens_match(cookie_token: str, header_token: str) -> bool:
	"""Double Submit CookieのCookie値とヘッダ値を定数時間比較する。"""
	return secrets.compare_digest(cookie_token, header_token)


_DUMMY_PASSWORD = "dummy-password-for-timing-attack-mitigation"


@lru_cache(maxsize=1)
def get_dummy_password_hash() -> str:
	"""ユーザー不存在時にも同じ検証コストを支払うためのダミーハッシュ（タイミング攻撃対策）。"""
	return hash_password(_DUMMY_PASSWORD)


__all__ = [
	"JwtDecodeError",
	"csrf_tokens_match",
	"decode_jwt",
	"encode_jwt",
	"get_dummy_password_hash",
	"hash_password",
	"needs_rehash",
	"verify_password",
]

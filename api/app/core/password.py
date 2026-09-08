from __future__ import annotations

from functools import lru_cache
from typing import cast

from passlib.context import CryptContext  # type: ignore[import-untyped]
from passlib.exc import UnknownHashError  # type: ignore[import-untyped]

from app.core.config import BackendSettings, get_backend_settings


def _context(settings: BackendSettings) -> CryptContext:
	return CryptContext(
		schemes=["argon2"],
		deprecated="auto",
		argon2__type="ID",
		argon2__time_cost=settings.argon2_time_cost,
		argon2__memory_cost=settings.argon2_memory_cost,
		argon2__parallelism=settings.argon2_parallelism,
	)


def hash_password(plain_password: str, settings: BackendSettings | None = None) -> str:
	return cast(str, _context(settings or get_backend_settings()).hash(plain_password))


def verify_password(
	plain_password: str,
	password_hash: str,
	settings: BackendSettings | None = None,
) -> bool:
	try:
		return bool(_context(settings or get_backend_settings()).verify(plain_password, password_hash))
	except UnknownHashError:
		return False
	except ValueError:
		return False


def needs_rehash(password_hash: str, settings: BackendSettings | None = None) -> bool:
	try:
		return bool(_context(settings or get_backend_settings()).needs_update(password_hash))
	except UnknownHashError:
		return False
	except ValueError:
		return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
	return hash_password("cerberus-dummy-password")

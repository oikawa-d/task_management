from __future__ import annotations

import pytest
from app.core import security
from app.core.config import get_backend_settings


def test_hash_and_verify_password_roundtrip() -> None:
	password_hash = security.hash_password("Str0ng!Passw0rd")

	assert security.verify_password("Str0ng!Passw0rd", password_hash) is True


def test_hash_password_does_not_return_plaintext() -> None:
	plain_password = "Str0ng!Passw0rd"

	password_hash = security.hash_password(plain_password)

	assert plain_password not in password_hash
	assert password_hash.startswith("$argon2id$")


def test_verify_password_rejects_wrong_password() -> None:
	password_hash = security.hash_password("Str0ng!Passw0rd")

	assert security.verify_password("wrong-password", password_hash) is False


def test_verify_password_rejects_malformed_hash() -> None:
	assert security.verify_password("Str0ng!Passw0rd", "not-a-valid-hash") is False


def test_needs_rehash_detects_cost_change(monkeypatch: pytest.MonkeyPatch) -> None:
	password_hash = security.hash_password("Str0ng!Passw0rd")
	assert security.needs_rehash(password_hash) is False

	monkeypatch.setenv("ARGON2_TIME_COST", "4")
	get_backend_settings.cache_clear()

	assert security.needs_rehash(password_hash) is True


def test_dummy_password_hash_is_stable_and_verifiable() -> None:
	dummy_hash_first = security.get_dummy_password_hash()
	dummy_hash_second = security.get_dummy_password_hash()

	assert dummy_hash_first == dummy_hash_second
	assert security.verify_password("any-plain-password", dummy_hash_first) is False

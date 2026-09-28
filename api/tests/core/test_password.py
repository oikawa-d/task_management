"""app.core.security のパスワードハッシュ化・検証・再ハッシュ判定に対する単体テスト。"""

from __future__ import annotations

import pytest
from app.core import security
from app.core.config import get_backend_settings


def test_hash_and_verify_password_roundtrip() -> None:
	"""平文パスワードをhash_passwordでハッシュ化し、同じ平文でverify_passwordがTrueを返すことを検証する。"""
	password_hash = security.hash_password("Str0ng!Passw0rd")

	assert security.verify_password("Str0ng!Passw0rd", password_hash) is True


def test_hash_password_does_not_return_plaintext() -> None:
	"""hash_passwordの戻り値に平文パスワードが含まれず、argon2idアルゴリズムで生成されていることを検証する。"""
	plain_password = "Str0ng!Passw0rd"

	password_hash = security.hash_password(plain_password)

	assert plain_password not in password_hash
	assert password_hash.startswith("$argon2id$")


def test_verify_password_rejects_wrong_password() -> None:
	"""正しいハッシュに対して誤った平文パスワードを検証した場合、verify_passwordがFalseを返すことを検証する。"""
	password_hash = security.hash_password("Str0ng!Passw0rd")

	assert security.verify_password("wrong-password", password_hash) is False


def test_verify_password_rejects_malformed_hash() -> None:
	"""ハッシュ形式が不正な文字列を検証した場合、例外を送出せずFalseを返すことを検証する。"""
	assert security.verify_password("Str0ng!Passw0rd", "not-a-valid-hash") is False


def test_needs_rehash_detects_cost_change(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Argon2のtime_cost設定を変更した場合、既存ハッシュに対してneeds_rehashがFalseからTrueへ変化することを検証する。

	Args:
		monkeypatch: 環境変数ARGON2_TIME_COSTを一時的に書き換えるためのpytest fixture。
	"""
	password_hash = security.hash_password("Str0ng!Passw0rd")
	assert security.needs_rehash(password_hash) is False

	monkeypatch.setenv("ARGON2_TIME_COST", "4")
	get_backend_settings.cache_clear()

	assert security.needs_rehash(password_hash) is True


def test_dummy_password_hash_is_stable_and_verifiable() -> None:
	"""get_dummy_password_hashが毎回同じダミーハッシュを返し（呼び出し間でキャッシュされ）、任意の平文で検証してもFalseになる(タイミング攻撃対策用の固定ハッシュ)ことを検証する。"""
	dummy_hash_first = security.get_dummy_password_hash()
	dummy_hash_second = security.get_dummy_password_hash()

	assert dummy_hash_first == dummy_hash_second
	assert security.verify_password("any-plain-password", dummy_hash_first) is False

from app.core.config import BackendSettings
from app.core.password import hash_password, needs_rehash, verify_password


def _settings(**overrides: object) -> BackendSettings:
	values = {
		"database_url": "postgresql+asyncpg://user:pass@localhost/db",
		"jwt_secret_key": "test-secret",
		"google_client_id": "client",
		"google_client_secret": "secret",
		"initial_admin_email": "admin@example.com",
		"initial_admin_username": "admin",
		"initial_admin_password": "password",
	}
	values.update(overrides)
	return BackendSettings(_env_file=None, **values)


def test_hash_password_uses_argon2id_and_verifies() -> None:
	password_hash = hash_password("Password1!", _settings())

	assert password_hash.startswith("$argon2id$")
	assert verify_password("Password1!", password_hash, _settings()) is True


def test_verify_password_rejects_wrong_password_and_invalid_hash() -> None:
	password_hash = hash_password("Password1!", _settings())

	assert verify_password("WrongPassword1!", password_hash, _settings()) is False
	assert verify_password("Password1!", "not-a-hash", _settings()) is False


def test_needs_rehash_detects_changed_cost() -> None:
	password_hash = hash_password("Password1!", _settings(argon2_time_cost=1))

	assert needs_rehash(password_hash, _settings(argon2_time_cost=3)) is True
	assert needs_rehash(password_hash, _settings(argon2_time_cost=1)) is False

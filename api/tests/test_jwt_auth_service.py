from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from app.core.config import BackendSettings
from app.core.exceptions import TokenExpiredError, TokenInvalidError, TokenRevokedError
from app.repository.refresh_token_repository import RefreshTokenData, TokenRotationResult
from app.service.jwt_auth_service import JwtAuthService


def settings() -> BackendSettings:
	return BackendSettings(
		database_url="postgresql+asyncpg://test:test@localhost/test",
		jwt_secret_key="unit-test-secret",
		google_client_id="client",
		google_client_secret="secret",
		initial_admin_email="admin@example.com",
		initial_admin_username="admin",
		initial_admin_password="password",
	)


class FakeRefreshRepository:
	def __init__(self) -> None:
		self.tokens: dict[str, RefreshTokenData] = {}
		self.used: dict[str, RefreshTokenData] = {}
		self.rotations: list[tuple[str, str]] = []
		self.revoked_families: list[tuple[object, str]] = []

	async def store(self, token: str, metadata: RefreshTokenData, ttl_seconds: int) -> None:
		self.tokens[token] = metadata

	async def get(self, token: str) -> RefreshTokenData | None:
		return self.tokens.get(token)

	async def get_used(self, token: str) -> RefreshTokenData | None:
		return self.used.get(token)

	async def rotate(
		self, old_token: str, new_token: str, metadata: RefreshTokenData, ttl_seconds: int
	) -> TokenRotationResult:
		old = self.tokens.pop(old_token, None)
		if old is None:
			return TokenRotationResult.REUSED
		self.used[old_token] = old
		self.tokens[new_token] = metadata
		self.rotations.append((old_token, new_token))
		return TokenRotationResult.ROTATED

	async def revoke_family(self, user_id, family_id: str, ttl_seconds: int) -> int:
		self.revoked_families.append((user_id, family_id))
		return 1


@pytest.mark.asyncio
async def test_issue_and_verify_access_token_checks_required_claims() -> None:
	repository = FakeRefreshRepository()
	service = JwtAuthService(settings(), repository)
	user_id = uuid4()

	tokens = await service.issue_tokens(user_id)
	claims = service.verify_access_token(tokens.access_token)

	assert claims["sub"] == str(user_id)
	assert claims["typ"] == "access"
	assert claims["jti"]
	assert tokens.refresh_token in repository.tokens


def test_verify_access_token_rejects_expired_token() -> None:
	service = JwtAuthService(settings(), FakeRefreshRepository())
	now = datetime.now(UTC)
	token = jwt.encode(
		{
			"sub": str(uuid4()),
			"iat": now - timedelta(minutes=2),
			"exp": now - timedelta(minutes=1),
			"jti": "jti",
			"typ": "access",
		},
		settings().jwt_secret_key,
		algorithm=settings().jwt_algorithm,
	)

	with pytest.raises(TokenExpiredError):
		service.verify_access_token(token)


def test_verify_access_token_rejects_wrong_signature_and_type() -> None:
	service = JwtAuthService(settings(), FakeRefreshRepository())
	now = datetime.now(UTC)
	wrong_key = jwt.encode(
		{"sub": str(uuid4()), "iat": now, "exp": now + timedelta(minutes=5), "jti": "jti", "typ": "access"},
		"wrong-secret",
		algorithm=settings().jwt_algorithm,
	)
	wrong_type = jwt.encode(
		{"sub": str(uuid4()), "iat": now, "exp": now + timedelta(minutes=5), "jti": "jti", "typ": "refresh"},
		settings().jwt_secret_key,
		algorithm=settings().jwt_algorithm,
	)

	with pytest.raises(TokenInvalidError):
		service.verify_access_token(wrong_key)
	with pytest.raises(TokenInvalidError):
		service.verify_access_token(wrong_type)


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_preserves_family() -> None:
	repository = FakeRefreshRepository()
	service = JwtAuthService(settings(), repository)
	initial = await service.issue_tokens(uuid4(), family_id="family-1")

	rotated = await service.refresh(initial.refresh_token)

	assert rotated.refresh_token != initial.refresh_token
	assert repository.rotations == [(initial.refresh_token, rotated.refresh_token)]
	assert repository.tokens[rotated.refresh_token].family_id == "family-1"


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_family_and_raises_without_secret_logging() -> None:
	repository = FakeRefreshRepository()
	service = JwtAuthService(settings(), repository)
	initial = await service.issue_tokens(uuid4(), family_id="family-1")
	await service.refresh(initial.refresh_token)

	with pytest.raises(TokenRevokedError):
		await service.refresh(initial.refresh_token)

	assert repository.revoked_families[0][1] == "family-1"

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import BackendSettings
from app.core.exceptions import TokenExpiredError, TokenInvalidError, TokenRevokedError
from app.repository.refresh_token_repository import (
	RefreshTokenData,
	RefreshTokenRepository,
	TokenRotationResult,
)


@dataclass(frozen=True)
class JwtTokenPair:
	access_token: str
	refresh_token: str
	expires_in: int
	family_id: str


class JwtAuthService:
	def __init__(self, settings: BackendSettings, refresh_tokens: RefreshTokenRepository) -> None:
		self.settings = settings
		self.refresh_tokens = refresh_tokens

	async def issue_tokens(
		self,
		user_id: UUID,
		family_id: str | None = None,
		now: datetime | None = None,
	) -> JwtTokenPair:
		issued_at = now or datetime.now(UTC)
		family = family_id or str(uuid4())
		access_token = self._encode_access_token(user_id, issued_at)
		refresh_token = secrets.token_urlsafe(48)
		await self.refresh_tokens.store(
			refresh_token,
			RefreshTokenData(
				user_id=user_id,
				jti=str(uuid4()),
				family_id=family,
				created_at=issued_at,
			),
			ttl_seconds=self.settings.refresh_ttl_seconds,
		)
		return JwtTokenPair(access_token, refresh_token, self.settings.access_token_ttl_seconds, family)

	def verify_access_token(self, token: str) -> dict[str, Any]:
		try:
			claims: dict[str, Any] = jwt.decode(
				token,
				self.settings.jwt_secret_key,
				algorithms=[self.settings.jwt_algorithm],
				options={"require": ["sub", "iat", "exp", "jti", "typ"]},
			)
		except ExpiredSignatureError:
			raise TokenExpiredError() from None
		except InvalidTokenError:
			raise TokenInvalidError() from None
		if claims.get("typ") != "access" or not isinstance(claims.get("sub"), str) or not claims["sub"]:
			raise TokenInvalidError()
		if not isinstance(claims.get("jti"), str) or not claims["jti"]:
			raise TokenInvalidError()
		return claims

	async def refresh(self, refresh_token: str) -> JwtTokenPair:
		metadata = await self.refresh_tokens.get(refresh_token)
		if metadata is None:
			used_metadata = await self.refresh_tokens.get_used(refresh_token)
			if used_metadata is not None:
				await self.refresh_tokens.revoke_family(
					used_metadata.user_id,
					used_metadata.family_id,
					ttl_seconds=self.settings.refresh_ttl_seconds,
				)
			raise TokenRevokedError()

		new_refresh_token = secrets.token_urlsafe(48)
		new_metadata = RefreshTokenData(
			user_id=metadata.user_id,
			jti=str(uuid4()),
			family_id=metadata.family_id,
			created_at=datetime.now(UTC),
		)
		result = await self.refresh_tokens.rotate(
			refresh_token,
			new_refresh_token,
			new_metadata,
			ttl_seconds=self.settings.refresh_ttl_seconds,
		)
		if result is not TokenRotationResult.ROTATED:
			await self.refresh_tokens.revoke_family(
				metadata.user_id,
				metadata.family_id,
				ttl_seconds=self.settings.refresh_ttl_seconds,
			)
			raise TokenRevokedError()

		access_token = self._encode_access_token(metadata.user_id, new_metadata.created_at)
		return JwtTokenPair(
			access_token,
			new_refresh_token,
			self.settings.access_token_ttl_seconds,
			metadata.family_id,
		)

	async def revoke_all(self, user_id: UUID) -> int:
		return await self.refresh_tokens.revoke_all(user_id)

	def _encode_access_token(self, user_id: UUID, issued_at: datetime) -> str:
		issued_timestamp = int(issued_at.timestamp())
		claims = {
			"sub": str(user_id),
			"iat": issued_timestamp,
			"exp": issued_timestamp + self.settings.access_token_ttl_seconds,
			"jti": str(uuid4()),
			"typ": "access",
		}
		return jwt.encode(claims, self.settings.jwt_secret_key, algorithm=self.settings.jwt_algorithm)

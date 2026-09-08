import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Awaitable, cast
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import BackendSettings


class TokenRotationResult(StrEnum):
	ROTATED = "rotated"
	REUSED = "reused"
	INVALID = "invalid"


@dataclass(frozen=True)
class RefreshTokenData:
	user_id: UUID
	jti: str
	family_id: str
	created_at: datetime

	@property
	def issued_at(self) -> datetime:
		return self.created_at

	def to_json(self) -> str:
		payload = asdict(self)
		payload["user_id"] = str(self.user_id)
		payload["created_at"] = self.created_at.isoformat()
		return json.dumps(payload, separators=(",", ":"))

	@classmethod
	def from_json(cls, raw: str | bytes) -> "RefreshTokenData":
		payload = json.loads(raw)
		return cls(
			user_id=UUID(payload["user_id"]),
			jti=str(payload["jti"]),
			family_id=str(payload["family_id"]),
			created_at=datetime.fromisoformat(payload["created_at"]),
		)


_ROTATE_SCRIPT = """
local old_value = redis.call('GET', KEYS[1])
local old_data = nil
if old_value then
    old_data = cjson.decode(old_value)
end
if not old_data then
    local used_value = redis.call('GET', KEYS[2])
    if used_value then
        old_data = cjson.decode(used_value)
        local family_key = ARGV[1] .. 'refresh_family_revoked:' .. old_data.user_id .. ':' .. old_data.family_id
        redis.call('SETEX', family_key, ARGV[4], '1')
        local members = redis.call('SMEMBERS', KEYS[4])
        for _, hash in ipairs(members) do
            local refresh_key = ARGV[1] .. 'refresh:' .. hash
            local value = redis.call('GET', refresh_key)
            if value then
                local data = cjson.decode(value)
                if data.user_id == old_data.user_id and data.family_id == old_data.family_id then
                    redis.call('DEL', refresh_key)
                    redis.call('SREM', KEYS[4], hash)
                end
            end
        end
        return {'reused', old_data.user_id, old_data.family_id}
    end
    return {'invalid', '', ''}
end

local family_key = ARGV[1] .. 'refresh_family_revoked:' .. old_data.user_id .. ':' .. old_data.family_id
if redis.call('EXISTS', family_key) == 1 then
    return {'reused', old_data.user_id, old_data.family_id}
end

redis.call('DEL', KEYS[1])
old_data.used_at = ARGV[5]
redis.call('SETEX', KEYS[2], ARGV[4], cjson.encode(old_data))
redis.call('SETEX', KEYS[3], ARGV[4], ARGV[3])
redis.call('SADD', KEYS[4], ARGV[2])
redis.call('EXPIRE', KEYS[4], ARGV[4])
return {'rotated', old_data.user_id, old_data.family_id}
"""


class RefreshTokenRepository:
	def __init__(
		self,
		redis_client: Redis,
		settings: BackendSettings | str | None = None,
		*,
		key_prefix: str | None = None,
	) -> None:
		self.redis = redis_client
		if key_prefix is not None:
			self.key_prefix = key_prefix
		elif isinstance(settings, str):
			self.key_prefix = settings
		else:
			self.key_prefix = settings.redis_key_prefix if settings is not None else ""

	@staticmethod
	def token_hash(token: str) -> str:
		return hashlib.sha256(token.encode("utf-8")).hexdigest()

	def key_for_token(self, token: str) -> str:
		return f"{self.key_prefix}refresh:{self.token_hash(token)}"

	def user_key(self, user_id: UUID) -> str:
		return f"{self.key_prefix}user_refresh:{user_id}"

	def used_key_for_token(self, token: str) -> str:
		return f"{self.key_prefix}refresh_used:{self.token_hash(token)}"

	async def store(self, token: str, metadata: RefreshTokenData, ttl_seconds: int) -> None:
		self._validate_ttl(ttl_seconds)
		token_hash = self.token_hash(token)
		pipeline = self.redis.pipeline(transaction=True)
		pipeline.set(self.key_for_token(token), metadata.to_json(), ex=ttl_seconds)
		pipeline.sadd(self.user_key(metadata.user_id), token_hash)
		pipeline.expire(self.user_key(metadata.user_id), ttl_seconds)
		await pipeline.execute()

	async def get(self, token: str) -> RefreshTokenData | None:
		raw = await self.redis.get(self.key_for_token(token))
		if raw is None:
			return None
		return RefreshTokenData.from_json(raw)

	async def get_used(self, token: str) -> RefreshTokenData | None:
		raw = await self.redis.get(self.used_key_for_token(token))
		if raw is None:
			return None
		return RefreshTokenData.from_json(raw)

	async def delete(self, token: str) -> bool:
		metadata = await self.get(token)
		if metadata is None:
			return False
		pipeline = self.redis.pipeline(transaction=True)
		pipeline.delete(self.key_for_token(token))
		pipeline.srem(self.user_key(metadata.user_id), self.token_hash(token))
		await pipeline.execute()
		return True

	async def rotate(
		self,
		old_token: str,
		new_token: str,
		new_metadata: RefreshTokenData,
		ttl_seconds: int,
	) -> TokenRotationResult:
		self._validate_ttl(ttl_seconds)
		result: list[Any] = await cast(
			Awaitable[list[Any]],
			self.redis.eval(
				_ROTATE_SCRIPT,
				4,
				self.key_for_token(old_token),
				self.used_key_for_token(old_token),
				self.key_for_token(new_token),
				self.user_key(new_metadata.user_id),
				self.key_prefix,
				self.token_hash(new_token),
				new_metadata.to_json(),
				str(ttl_seconds),
				datetime.now(new_metadata.created_at.tzinfo).isoformat(),
			),
		)
		return TokenRotationResult(result[0].decode() if isinstance(result[0], bytes) else result[0])

	async def revoke_family(self, user_id: UUID, family_id: str, ttl_seconds: int) -> int:
		self._validate_ttl(ttl_seconds)
		user_key = self.user_key(user_id)
		members = await cast(Awaitable[set[Any]], self.redis.smembers(user_key))
		matched_hashes: list[str] = []
		for member in members:
			token_hash = member.decode() if isinstance(member, bytes) else member
			raw = await self.redis.get(f"{self.key_prefix}refresh:{token_hash}")
			if raw is not None and RefreshTokenData.from_json(raw).family_id == family_id:
				matched_hashes.append(token_hash)

		family_key = f"{self.key_prefix}refresh_family_revoked:{user_id}:{family_id}"
		pipeline = self.redis.pipeline(transaction=True)
		pipeline.set(family_key, "1", ex=ttl_seconds)
		for token_hash in matched_hashes:
			pipeline.delete(f"{self.key_prefix}refresh:{token_hash}")
			pipeline.srem(user_key, token_hash)
		await pipeline.execute()
		return len(matched_hashes)

	async def revoke_all(self, user_id: UUID) -> int:
		user_key = self.user_key(user_id)
		members = await cast(Awaitable[set[Any]], self.redis.smembers(user_key))
		pipeline = self.redis.pipeline(transaction=True)
		for member in members:
			token_hash = member.decode() if isinstance(member, bytes) else member
			pipeline.delete(f"{self.key_prefix}refresh:{token_hash}")
		pipeline.delete(user_key)
		await pipeline.execute()
		return len(members)

	@staticmethod
	def _validate_ttl(ttl_seconds: int) -> None:
		if ttl_seconds <= 0:
			raise ValueError("ttl_seconds must be positive")

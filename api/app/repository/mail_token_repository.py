import hashlib
import json
import uuid
from typing import Any

from redis.asyncio import Redis

_REPLACE_TOKEN_SCRIPT = """
local old_hash = redis.call('GET', KEYS[1])
if old_hash then
    redis.call('DEL', ARGV[1] .. old_hash)
end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[1], ARGV[4], 'EX', ARGV[3])
return 1
"""

_CONSUME_CURRENT_TOKEN_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if not value then
	return false
end
local data = cjson.decode(value)
local current_key = ARGV[1] .. data.user_id
if redis.call('GET', current_key) ~= ARGV[2] then
	return false
end
if value then
	redis.call('DEL', KEYS[1])
	redis.call('DEL', current_key)
end
return value
"""


class MailTokenRepository:
	def __init__(self, redis: Redis, key_prefix: str = "") -> None:
		self._redis: Any = redis
		self._prefix = key_prefix

	@staticmethod
	def hash_token(token: str) -> str:
		return hashlib.sha256(token.encode("utf-8")).hexdigest()

	def _key(self, name: str, identifier: str) -> str:
		return f"{self._prefix}{name}:{identifier}"

	@staticmethod
	def _decode(value: Any) -> str | None:
		if value is None:
			return None
		return value.decode("utf-8") if isinstance(value, bytes) else str(value)

	@classmethod
	def _user_id_from_value(cls, value: Any) -> uuid.UUID | None:
		decoded = cls._decode(value)
		if decoded is None:
			return None
		payload = json.loads(decoded)
		return uuid.UUID(str(payload["user_id"]))

	async def save_email_verification_token(self, token: str, user_id: uuid.UUID, ttl: int) -> None:
		token_hash = self.hash_token(token)
		payload = json.dumps({"user_id": str(user_id)}, separators=(",", ":"))
		await self._redis.eval(
			_REPLACE_TOKEN_SCRIPT,
			2,
			self._key("emailverify_current", str(user_id)),
			self._key("emailverify", token_hash),
			self._key("emailverify", "").rstrip(":"),
			payload,
			str(ttl),
			token_hash,
		)

	async def replace_email_verify_token(self, token: str, user_id: uuid.UUID, ttl: int) -> None:
		await self.save_email_verification_token(token, user_id, ttl)

	async def consume_email_verification_token(self, token: str) -> uuid.UUID | None:
		value = await self._redis.getdel(self._key("emailverify", self.hash_token(token)))
		return self._user_id_from_value(value)

	async def consume_email_verify_token(self, token: str) -> uuid.UUID | None:
		return await self.consume_email_verification_token(token)

	async def is_email_verification_resend_allowed(self, user_id: uuid.UUID) -> bool:
		return not bool(await self._redis.exists(self._key("emailverify_sent", str(user_id))))

	async def is_email_verify_resend_allowed(self, user_id: uuid.UUID) -> bool:
		return await self.is_email_verification_resend_allowed(user_id)

	async def mark_email_verification_sent(self, user_id: uuid.UUID, interval: int) -> bool:
		result = await self._redis.set(self._key("emailverify_sent", str(user_id)), "1", nx=True, ex=interval)
		return bool(result)

	async def mark_email_verify_sent(self, user_id: uuid.UUID, interval: int) -> bool:
		return await self.mark_email_verification_sent(user_id, interval)

	async def save_password_reset_token(self, token: str, user_id: uuid.UUID, ttl: int) -> None:
		token_hash = self.hash_token(token)
		payload = json.dumps({"user_id": str(user_id)}, separators=(",", ":"))
		await self._redis.eval(
			_REPLACE_TOKEN_SCRIPT,
			2,
			self._key("pwreset_current", str(user_id)),
			self._key("pwreset", token_hash),
			self._key("pwreset", "").rstrip(":"),
			payload,
			str(ttl),
			token_hash,
		)

	async def consume_password_reset_token(self, token: str) -> uuid.UUID | None:
		token_hash = self.hash_token(token)
		value = await self._redis.eval(
			_CONSUME_CURRENT_TOKEN_SCRIPT,
			1,
			self._key("pwreset", token_hash),
			self._key("pwreset_current", "").rstrip(":") + ":",
			token_hash,
		)
		return self._user_id_from_value(value)

	async def delete_all_sessions(self, user_id: uuid.UUID) -> int:
		set_key = self._key("user_sessions", str(user_id))
		decoded_members = [self._decode(value) for value in await self._redis.smembers(set_key)]
		members = [value for value in decoded_members if value is not None]
		keys = [key for member in members for key in (self._key("session", member), self._key("csrf", member))]
		keys.append(set_key)
		await self._redis.delete(*keys)
		return len(members)

	async def revoke_all_refresh_tokens(self, user_id: uuid.UUID) -> int:
		set_key = self._key("user_refresh", str(user_id))
		decoded_members = [self._decode(value) for value in await self._redis.smembers(set_key)]
		members = [value for value in decoded_members if value is not None]
		keys = [self._key("refresh", member) for member in members]
		keys.append(set_key)
		await self._redis.delete(*keys)
		return len(members)

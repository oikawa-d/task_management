from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_backend_settings
from app.repository.redis_store_common import (
	OAuthHandoffData,
	OAuthStateData,
	RefreshData,
	TokenReused,
	dump,
	key,
	parse_datetime,
	parse_json,
	token_hash,
	validate_ttl,
)

_ROTATE_REFRESH_SCRIPT = (Path(__file__).parent / "redis_scripts" / "rotate_refresh_token.lua").read_text(
	encoding="utf-8"
)

_SAVE_PASSWORD_RESET_SCRIPT = """
if ARGV[1] ~= '' and redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('DEL', KEYS[2])
redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[4])
return 1
"""

_CONSUME_PASSWORD_RESET_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if not value then return '' end
local data = cjson.decode(value)
local current_key = ARGV[1] .. 'pwreset_current:' .. data.user_id
if redis.call('GET', current_key) ~= ARGV[2] then return '' end
redis.call('DEL', KEYS[1], current_key)
return data.user_id
"""


async def store_refresh_token(client: Redis, prefix: str, token: str, user_id: UUID, family_id: str, ttl: int) -> None:
	validate_ttl(ttl)
	token_hash_value = token_hash(token)
	pipe = client.pipeline(transaction=True)
	pipe.setex(
		key("refresh", prefix, token_hash_value),
		ttl,
		dump({"user_id": user_id, "issued_at": datetime.now(UTC).isoformat(), "family_id": family_id}),
	)
	pipe.sadd(key("user_refresh", prefix, user_id), token_hash_value)
	pipe.expire(key("user_refresh", prefix, user_id), ttl)
	await pipe.execute()


async def get_refresh_token(client: Redis, prefix: str, token: str) -> RefreshData | None:
	data = parse_json(await cast(Any, client.get)(key("refresh", prefix, token_hash(token))))
	if data is None:
		return None
	return RefreshData(UUID(str(data["user_id"])), parse_datetime(data["issued_at"]), str(data["family_id"]))


async def rotate_refresh_token(
	client: Redis, prefix: str, old_token: str, new_token: str, ttl: int
) -> RefreshData | TokenReused | None:
	validate_ttl(ttl)
	old_hash = token_hash(old_token)
	new_hash = token_hash(new_token)
	now = datetime.now(UTC)
	result: list[Any] = await cast(Any, client.eval)(
		_ROTATE_REFRESH_SCRIPT,
		3,
		key("refresh", prefix, old_hash),
		key("refresh", prefix, new_hash),
		key("refresh_used", prefix, old_hash),
		old_hash,
		new_hash,
		dump({"issued_at": now.isoformat()}),
		ttl,
		now.isoformat(),
		prefix,
	)
	if not result or int(result[0]) == 0:
		return None
	user_id = UUID(str(result[1]))
	family_id = str(result[2])
	if int(result[0]) == 2:
		return TokenReused(user_id, family_id)
	return RefreshData(user_id, now, family_id)


async def revoke_refresh_token(client: Redis, prefix: str, token: str, user_id: UUID) -> None:
	token_hash_value = token_hash(token)
	pipe = client.pipeline(transaction=True)
	pipe.delete(key("refresh", prefix, token_hash_value))
	pipe.srem(key("user_refresh", prefix, user_id), token_hash_value)
	await pipe.execute()


async def revoke_token_family(client: Redis, prefix: str, user_id: UUID, family_id: str, ttl: int | None = None) -> int:
	if ttl is None:
		ttl = get_backend_settings().refresh_ttl_seconds
	validate_ttl(ttl)
	raw_token_hashes = await cast(Any, client.smembers)(key("user_refresh", prefix, user_id))
	token_hashes = [
		token_hash.decode() if isinstance(token_hash, bytes) else str(token_hash) for token_hash in raw_token_hashes
	]
	to_delete: list[str] = []
	for token_hash_value in token_hashes:
		data = parse_json(await cast(Any, client.get)(key("refresh", prefix, token_hash_value)))
		if data and str(data.get("family_id")) == family_id:
			to_delete.append(token_hash_value)
	pipe = client.pipeline(transaction=True)
	pipe.setex(key("refresh_family_revoked", prefix, user_id, family_id), ttl, "1")
	for token_hash_value in to_delete:
		pipe.delete(key("refresh", prefix, token_hash_value))
		pipe.srem(key("user_refresh", prefix, user_id), token_hash_value)
	await pipe.execute()
	return len(to_delete)


async def revoke_all_refresh_tokens(client: Redis, prefix: str, user_id: UUID) -> int:
	raw_token_hashes = await cast(Any, client.smembers)(key("user_refresh", prefix, user_id))
	token_hashes = [
		token_hash.decode() if isinstance(token_hash, bytes) else str(token_hash) for token_hash in raw_token_hashes
	]
	pipe = client.pipeline(transaction=True)
	for token_hash_value in token_hashes:
		pipe.delete(key("refresh", prefix, token_hash_value))
	pipe.delete(key("user_refresh", prefix, user_id))
	await pipe.execute()
	return len(token_hashes)


async def save_oauth_state(
	client: Redis, prefix: str, state: str, redirect_to: str, code_verifier: str, nonce: str, ttl: int
) -> None:
	validate_ttl(ttl)
	await client.setex(
		key("oauth_state", prefix, state),
		ttl,
		dump(
			{
				"redirect_to": redirect_to,
				"code_verifier": code_verifier,
				"nonce": nonce,
				"created_at": datetime.now(UTC).isoformat(),
			}
		),
	)


async def consume_oauth_state(client: Redis, prefix: str, state: str) -> OAuthStateData | None:
	data = parse_json(await client.getdel(key("oauth_state", prefix, state)))
	if data is None:
		return None
	return OAuthStateData(
		str(data["redirect_to"]), str(data["code_verifier"]), str(data["nonce"]), parse_datetime(data["created_at"])
	)


async def save_oauth_handoff(client: Redis, prefix: str, code: str, user_id: UUID, redirect_to: str, ttl: int) -> None:
	validate_ttl(ttl)
	await client.setex(
		key("oauth_handoff", prefix, code),
		ttl,
		dump({"user_id": user_id, "redirect_to": redirect_to, "created_at": datetime.now(UTC).isoformat()}),
	)


async def consume_oauth_handoff(client: Redis, prefix: str, code: str) -> OAuthHandoffData | None:
	data = parse_json(await client.getdel(key("oauth_handoff", prefix, code)))
	if data is None:
		return None
	return OAuthHandoffData(UUID(str(data["user_id"])), str(data["redirect_to"]), parse_datetime(data["created_at"]))


async def save_password_reset_token(client: Redis, prefix: str, token: str, user_id: UUID, ttl: int) -> None:
	validate_ttl(ttl)
	token_hash_value = token_hash(token)
	current_key = key("pwreset_current", prefix, user_id)
	old_hash = await cast(Any, client.get)(current_key) or ""
	await cast(Any, client.eval)(
		_SAVE_PASSWORD_RESET_SCRIPT,
		3,
		current_key,
		key("pwreset", prefix, old_hash or token_hash_value),
		key("pwreset", prefix, token_hash_value),
		old_hash,
		token_hash_value,
		dump({"user_id": user_id, "requested_at": datetime.now(UTC).isoformat()}),
		ttl,
	)


async def consume_password_reset_token(client: Redis, prefix: str, token: str) -> UUID | None:
	token_hash_value = token_hash(token)
	result = await cast(Any, client.eval)(
		_CONSUME_PASSWORD_RESET_SCRIPT,
		1,
		key("pwreset", prefix, token_hash_value),
		prefix,
		token_hash_value,
	)
	if not result:
		return None
	return UUID(str(result.decode() if isinstance(result, bytes) else result))


async def replace_email_verify_token(client: Redis, prefix: str, token: str, user_id: UUID, ttl: int) -> None:
	validate_ttl(ttl)
	token_hash_value = token_hash(token)
	current_key = key("emailverify_current", prefix, user_id)
	old_hash = await cast(Any, client.get)(current_key)
	pipe = client.pipeline(transaction=True)
	if old_hash:
		pipe.delete(key("emailverify", prefix, old_hash))
	pipe.setex(
		key("emailverify", prefix, token_hash_value),
		ttl,
		dump({"user_id": user_id, "requested_at": datetime.now(UTC).isoformat()}),
	)
	pipe.setex(current_key, ttl, token_hash_value)
	await pipe.execute()


async def consume_email_verify_token(client: Redis, prefix: str, token: str) -> UUID | None:
	data = parse_json(await client.getdel(key("emailverify", prefix, token_hash(token))))
	return UUID(str(data["user_id"])) if data else None

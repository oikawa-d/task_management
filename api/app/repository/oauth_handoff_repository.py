import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, cast
from urllib.parse import urlsplit
from uuid import UUID

from app.core.config import get_backend_settings
from app.redis_client import get_redis_client


class RedisOAuthClient(Protocol):
	async def setex(self, name: str, time: int, value: str) -> Any: ...

	async def getdel(self, name: str) -> str | bytes | None: ...


@dataclass(frozen=True)
class OAuthHandoffData:
	user_id: UUID
	redirect_to: str
	created_at: datetime


def _redis(redis: RedisOAuthClient | None) -> RedisOAuthClient:
	return cast(RedisOAuthClient, redis if redis is not None else get_redis_client())


def _key(code: str) -> str:
	return f"{get_backend_settings().redis_key_prefix}oauth_handoff:{code}"


def _validate_redirect(redirect_to: str) -> None:
	parsed = urlsplit(redirect_to)
	if not redirect_to.startswith("/") or redirect_to.startswith("//") or parsed.scheme or parsed.netloc:
		raise ValueError("redirect_to must be a relative path")


async def save_oauth_handoff(
	code: str,
	user_id: UUID,
	redirect_to: str,
	ttl: int,
	*,
	redis: RedisOAuthClient | None = None,
) -> None:
	if not code or not isinstance(user_id, UUID):
		raise ValueError("handoff code must not be empty")
	_validate_redirect(redirect_to)
	value = json.dumps(
		{
			"user_id": str(user_id),
			"redirect_to": redirect_to,
			"created_at": datetime.now(timezone.utc).isoformat(),
		},
		separators=(",", ":"),
	)
	await _redis(redis).setex(_key(code), ttl, value)


async def consume_oauth_handoff(code: str, *, redis: RedisOAuthClient | None = None) -> OAuthHandoffData | None:
	if not code:
		return None
	raw = await _redis(redis).getdel(_key(code))
	if raw is None:
		return None
	try:
		value = json.loads(raw)
		if not isinstance(value, dict):
			raise ValueError("OAuth handoff must be an object")
		_validate_redirect(value["redirect_to"])
		return OAuthHandoffData(
			user_id=UUID(value["user_id"]),
			redirect_to=value["redirect_to"],
			created_at=datetime.fromisoformat(value["created_at"]),
		)
	except Exception:
		return None

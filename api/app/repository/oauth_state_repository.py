import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

from app.core.config import get_backend_settings
from app.redis_client import get_redis_client


class RedisOAuthClient(Protocol):
	async def setex(self, name: str, time: int, value: str) -> Any: ...

	async def getdel(self, name: str) -> str | bytes | None: ...


@dataclass(frozen=True)
class OAuthStateData:
	redirect_to: str
	code_verifier: str
	nonce: str
	created_at: datetime


def _redis(redis: RedisOAuthClient | None) -> RedisOAuthClient:
	return cast(RedisOAuthClient, redis if redis is not None else get_redis_client())


def _key(state: str) -> str:
	return f"{get_backend_settings().redis_key_prefix}oauth_state:{state}"


def _validate_redirect(redirect_to: str) -> None:
	parsed = urlsplit(redirect_to)
	if not redirect_to.startswith("/") or redirect_to.startswith("//") or parsed.scheme or parsed.netloc:
		raise ValueError("redirect_to must be a relative path")


def _decode(raw: str | bytes) -> OAuthStateData:
	value = json.loads(raw)
	if not isinstance(value, dict):
		raise ValueError("OAuth state must be an object")
	_validate_redirect(value["redirect_to"])
	return OAuthStateData(
		redirect_to=value["redirect_to"],
		code_verifier=value["code_verifier"],
		nonce=value["nonce"],
		created_at=datetime.fromisoformat(value["created_at"]),
	)


async def save_oauth_state(
	state: str,
	redirect_to: str,
	code_verifier: str,
	nonce: str,
	ttl: int,
	*,
	redis: RedisOAuthClient | None = None,
) -> None:
	if not state or not code_verifier or not nonce:
		raise ValueError("OAuth state fields must not be empty")
	_validate_redirect(redirect_to)
	value = json.dumps(
		{
			"redirect_to": redirect_to,
			"code_verifier": code_verifier,
			"nonce": nonce,
			"created_at": datetime.now(timezone.utc).isoformat(),
		},
		separators=(",", ":"),
	)
	await _redis(redis).setex(_key(state), ttl, value)


async def consume_oauth_state(state: str, *, redis: RedisOAuthClient | None = None) -> OAuthStateData | None:
	if not state:
		return None
	raw = await _redis(redis).getdel(_key(state))
	if raw is None:
		return None
	try:
		return _decode(raw)
	except Exception:
		return None

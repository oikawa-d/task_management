from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID


@dataclass(frozen=True)
class SessionData:
	user_id: UUID
	created_at: datetime
	ip: str | None


@dataclass(frozen=True)
class RefreshData:
	user_id: UUID
	issued_at: datetime
	family_id: str


@dataclass(frozen=True)
class TokenReused:
	user_id: UUID
	family_id: str


@dataclass(frozen=True)
class OAuthStateData:
	redirect_to: str
	code_verifier: str
	nonce: str
	created_at: datetime


@dataclass(frozen=True)
class OAuthHandoffData:
	user_id: UUID
	redirect_to: str
	created_at: datetime


def key(name: str, prefix: str, *parts: object) -> str:
	suffix = ":".join((name, *(str(part) for part in parts)))
	return f"{prefix}{suffix}"


def token_hash(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def identifier_hash(identifier: str, client_ip: str) -> str:
	normalized = identifier.strip().lower()
	return hashlib.sha256(f"{normalized}:{client_ip}".encode()).hexdigest()


def rate_limit_key(scope: str, value: str, prefix: str) -> str:
	return key("rate_limit", prefix, scope, hashlib.sha256(value.encode()).hexdigest())


def parse_json(value: str | bytes | None) -> dict[str, Any] | None:
	if value is None:
		return None
	if isinstance(value, bytes):
		value = value.decode()
	return cast(dict[str, Any], json.loads(value))


def dump(data: dict[str, object]) -> str:
	return json.dumps(data, separators=(",", ":"), default=str)


def validate_ttl(ttl: int, name: str = "ttl") -> None:
	if ttl <= 0:
		raise ValueError(f"{name} must be positive")


def parse_datetime(value: object) -> datetime:
	parsed = datetime.fromisoformat(str(value))
	return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

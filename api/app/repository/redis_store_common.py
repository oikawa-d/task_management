"""Redisストア関連モジュール共通のデータ型・キー生成・シリアライズ用ヘルパー。

本モジュール自体はRedis/DBへのI/Oを行わない。Redisキー命名規則の統一、値のハッシュ化・
JSON変換、TTL検証など、他のredis_store系モジュールから利用される純粋関数のみを提供する。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID


@dataclass(frozen=True)
class SessionData:
	"""セッションストアに保持するセッション1件分のデータ。"""

	user_id: UUID
	created_at: datetime
	ip: str | None


@dataclass(frozen=True)
class RefreshData:
	"""リフレッシュトークンストアに保持するトークン1件分のデータ。"""

	user_id: UUID
	issued_at: datetime
	family_id: str


@dataclass(frozen=True)
class TokenReused:
	"""リフレッシュトークンの再利用(トークンローテーション不正)を検知した際の情報。"""

	user_id: UUID
	family_id: str


@dataclass(frozen=True)
class OAuthStateData:
	"""OAuth認可フロー中に一時保持するstate/PKCE検証用データ。"""

	redirect_to: str
	code_verifier: str
	nonce: str
	created_at: datetime


@dataclass(frozen=True)
class OAuthHandoffData:
	"""OAuthログイン完了後、フロントエンドへの引き渡し用に一時保持するデータ。"""

	user_id: UUID
	redirect_to: str
	created_at: datetime


def key(name: str, prefix: str, *parts: object) -> str:
	"""Redisキーをプレフィックス・名前・可変長パーツから組み立てる。

	Args:
		name: キーの種別を表す名前(例: "session")。
		prefix: 環境やサービスを識別するキープレフィックス。
		*parts: `:`区切りで連結する追加のキー要素(セッションID等)。

	Returns:
		`{prefix}{name}:{part1}:{part2}...`形式のRedisキー文字列。
	"""
	suffix = ":".join((name, *(str(part) for part in parts)))
	return f"{prefix}{suffix}"


def token_hash(token: str) -> str:
	"""トークン文字列をSHA-256でハッシュ化する。

	生のトークン値をRedisキーや値として保存しないようにするための変換に用いる。

	Args:
		token: ハッシュ化対象のトークン文字列。

	Returns:
		SHA-256ハッシュの16進数文字列。
	"""
	return hashlib.sha256(token.encode()).hexdigest()


def identifier_hash(identifier: str, client_ip: str) -> str:
	"""ログイン識別子とクライアントIPからレート制限用のハッシュ値を生成する。

	識別子は前後空白除去・小文字化により正規化してからハッシュ化する。

	Args:
		identifier: ログイン識別子(ユーザー名・メールアドレス等)。
		client_ip: クライアントのIPアドレス。

	Returns:
		SHA-256ハッシュの16進数文字列。
	"""
	normalized = identifier.strip().lower()
	return hashlib.sha256(f"{normalized}:{client_ip}".encode()).hexdigest()


def rate_limit_key(scope: str, value: str, prefix: str) -> str:
	"""レート制限カウンタ用のRedisキーを組み立てる。

	Args:
		scope: レート制限の対象範囲を示す識別子(例: "login")。
		value: 制限対象の値(識別子ハッシュ等)。ハッシュ化してキーに含める。
		prefix: 環境やサービスを識別するキープレフィックス。

	Returns:
		`rate_limit`名前空間のRedisキー文字列。
	"""
	return key("rate_limit", prefix, scope, hashlib.sha256(value.encode()).hexdigest())


def parse_json(value: str | bytes | None) -> dict[str, Any] | None:
	"""Redisから取得したJSON文字列(またはbytes)を辞書へ変換する。

	Args:
		value: Redisから取得した値。未設定(キー無し)の場合はNone。

	Returns:
		パース済みの辞書。`value`がNoneの場合はNone。

	Raises:
		json.JSONDecodeError: `value`が不正なJSONの場合。
	"""
	if value is None:
		return None
	if isinstance(value, bytes):
		value = value.decode()
	return cast(dict[str, Any], json.loads(value))


def dump(data: dict[str, object]) -> str:
	"""辞書をRedis保存用のコンパクトなJSON文字列へシリアライズする。

	Args:
		data: シリアライズ対象の辞書。

	Returns:
		区切り文字を詰めたJSON文字列(`datetime`等は`str()`で文字列化する)。
	"""
	return json.dumps(data, separators=(",", ":"), default=str)


def validate_ttl(ttl: int, name: str = "ttl") -> None:
	"""TTL(有効期限秒数)が正の値であることを検証する。

	Args:
		ttl: 検証対象のTTL値(秒)。
		name: エラーメッセージに含めるパラメータ名。

	Returns:
		None。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
	if ttl <= 0:
		raise ValueError(f"{name} must be positive")


def parse_datetime(value: object) -> datetime:
	"""ISO 8601形式の値をtimezone-awareなdatetimeへ変換する。

	タイムゾーン情報を含まない値はUTCとみなして補完する。

	Args:
		value: ISO 8601形式の文字列に変換可能な値(str()適用後にパースする)。

	Returns:
		timezone-awareなdatetime。

	Raises:
		ValueError: `value`をISO 8601形式としてパースできない場合。
	"""
	parsed = datetime.fromisoformat(str(value))
	return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

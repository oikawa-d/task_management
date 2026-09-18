"""セッション情報のRedis永続化を扱うデータアクセス層。

読み書きするRedisキーは`{prefix}session:{session_id}`(セッション本体)、
`{prefix}csrf:{session_id}`(CSRFトークン)、`{prefix}user_sessions:{user_id}`
(ユーザーが保持するセッションIDのSet)の3種類。各関数はRedisコマンドの実行のみを行い、
DBのようなトランザクションのcommit/rollbackという概念は持たない
(パイプラインで発行するコマンドはRedis側でまとめて適用される)。
"""

from __future__ import annotations

import math
import secrets
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.repository.redis_store_common import (
	SessionData,
	dump,
	key,
	parse_datetime,
	parse_json,
	validate_ttl,
)


async def create_session(client: Redis, prefix: str, user_id: UUID, ip: str | None, ttl: int) -> tuple[str, str]:
	"""新規セッションを作成し、セッションIDとCSRFトークンを発行する。

	`session:{session_id}`・`csrf:{session_id}`をそれぞれTTL付きで新規作成し、
	`user_sessions:{user_id}`(Set)にセッションIDを追加してTTLを設定する副作用を持つ。
	4つのRedisコマンドをパイプライン(トランザクション)でまとめて実行する。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		user_id: セッションの所有者となるユーザーID。
		ip: セッション作成時の接続元IPアドレス。取得できない場合はNone。
		ttl: セッションの有効期限(秒)。

	Returns:
		(セッションID, CSRFトークン)のタプル。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
	validate_ttl(ttl)
	session_id = secrets.token_urlsafe(32)
	csrf_token = secrets.token_urlsafe(32)
	created_at = datetime.now(UTC)
	pipe = client.pipeline(transaction=True)
	pipe.setex(
		key("session", prefix, session_id),
		ttl,
		dump({"user_id": user_id, "created_at": created_at.isoformat(), "ip": ip}),
	)
	pipe.setex(key("csrf", prefix, session_id), ttl, dump({"token": csrf_token}))
	pipe.sadd(key("user_sessions", prefix, user_id), session_id)
	pipe.expire(key("user_sessions", prefix, user_id), ttl)
	await pipe.execute()
	return session_id, csrf_token


async def get_session(client: Redis, prefix: str, session_id: str) -> SessionData | None:
	"""セッションIDを指定してセッション情報を取得する。

	`session:{session_id}`キーの値を取得する(読み取りのみ、副作用なし)。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		session_id: 検索対象のセッションID。

	Returns:
		該当するSessionData。キーが存在しない(未作成または期限切れ)場合はNone。
	"""
	data = parse_json(await client.get(key("session", prefix, session_id)))
	if data is None:
		return None
	return SessionData(
		user_id=UUID(str(data["user_id"])),
		created_at=parse_datetime(data["created_at"]),
		ip=cast(str | None, data.get("ip")),
	)


async def touch_session(
	client: Redis, prefix: str, session_id: str, user_id: UUID, ttl: int, absolute_expires_at: datetime
) -> bool:
	"""セッションの有効期限を延長する(スライディングセッション更新)。

	`session:{session_id}`・`csrf:{session_id}`・`user_sessions:{user_id}`の3キーの
	TTLを、指定TTLと絶対有効期限までの残り秒数のいずれか短い方で更新する副作用を持つ。
	セッションが既に存在しない場合、または絶対有効期限を過ぎている場合は更新しない。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		session_id: 対象のセッションID。
		user_id: セッションの所有者のユーザーID。
		ttl: 延長する有効期限(秒)。
		absolute_expires_at: セッションの絶対有効期限(この時刻を超えて延長しない)。

	Returns:
		延長できた場合はTrue。セッションが存在しない、または絶対有効期限を
		過ぎている場合はFalse。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
	validate_ttl(ttl)
	if await client.get(key("session", prefix, session_id)) is None:
		return False
	remaining = (absolute_expires_at - datetime.now(UTC)).total_seconds()
	if remaining <= 0:
		return False
	effective_ttl = min(ttl, math.ceil(remaining))
	pipe = client.pipeline(transaction=True)
	pipe.expire(key("session", prefix, session_id), effective_ttl)
	pipe.expire(key("csrf", prefix, session_id), effective_ttl)
	pipe.expire(key("user_sessions", prefix, user_id), effective_ttl)
	await pipe.execute()
	return True


async def get_csrf_token(client: Redis, prefix: str, session_id: str) -> str | None:
	"""セッションに紐づくCSRFトークンを取得する。

	`csrf:{session_id}`キーの値を取得する(読み取りのみ、副作用なし)。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		session_id: 対象のセッションID。

	Returns:
		該当するCSRFトークン文字列。キーが存在しない場合はNone。
	"""
	data = parse_json(await client.get(key("csrf", prefix, session_id)))
	return cast(str | None, data.get("token")) if data else None


async def delete_session(client: Redis, prefix: str, session_id: str, user_id: UUID) -> None:
	"""セッションを1件削除する(ログアウト等)。

	`session:{session_id}`・`csrf:{session_id}`を削除し、`user_sessions:{user_id}`
	(Set)から該当セッションIDを取り除く副作用を持つ。対象キーが既に存在しない場合も
	エラーにはならない。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		session_id: 削除対象のセッションID。
		user_id: セッションの所有者のユーザーID。

	Returns:
		None。
	"""
	pipe = client.pipeline(transaction=True)
	pipe.delete(key("session", prefix, session_id), key("csrf", prefix, session_id))
	pipe.srem(key("user_sessions", prefix, user_id), session_id)
	await pipe.execute()


async def delete_all_sessions(client: Redis, prefix: str, user_id: UUID) -> int:
	"""指定ユーザーの全セッションを削除する(全端末ログアウト等)。

	`user_sessions:{user_id}`(Set)からセッションID一覧を取得し、各セッションに対応する
	`session:{session_id}`・`csrf:{session_id}`と、`user_sessions:{user_id}`自体を
	削除する副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		user_id: 対象のユーザーID。

	Returns:
		削除したセッションの件数(セッションが1件も無い場合は0)。
	"""
	raw_session_ids = await cast(Any, client.smembers)(key("user_sessions", prefix, user_id))
	session_ids = [
		session_id.decode() if isinstance(session_id, bytes) else str(session_id) for session_id in raw_session_ids
	]
	pipe = client.pipeline(transaction=True)
	for session_id in session_ids:
		pipe.delete(key("session", prefix, session_id), key("csrf", prefix, session_id))
	pipe.delete(key("user_sessions", prefix, user_id))
	await pipe.execute()
	return len(session_ids)

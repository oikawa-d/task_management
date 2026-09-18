"""ログイン失敗回数・レート制限・メール確認送信間隔をRedisで管理するデータアクセス層。

読み書きするRedisキーは`{prefix}emailverify_sent:{user_id}`(メール確認送信間隔制御)、
`{prefix}login_fail:{identifier_hash}`(ログイン失敗カウンタ)、
`{prefix}rate_limit:{scope}:{value_hash}`(汎用レート制限カウンタ)の3種類。
各関数はRedisコマンドの実行のみを行い、DBのようなトランザクションのcommit/rollback
という概念は持たない。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from redis.asyncio import Redis

from app.repository.redis_store_common import identifier_hash, key, rate_limit_key, validate_ttl


async def mark_email_verify_sent(client: Redis, prefix: str, user_id: UUID, interval: int) -> bool:
	"""メール確認メールの再送を、指定間隔内は禁止するためのマーカーを設定する。

	`emailverify_sent:{user_id}`キーを`NX`(未設定の場合のみ)かつTTL付きで設定する
	副作用を持つ。既にキーが存在する場合は何も変更しない。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		user_id: 対象のユーザーID。
		interval: 再送を禁止する間隔(秒)。

	Returns:
		マーカーを新規設定できた場合(=送信してよい場合)はTrue。
		既にマーカーが存在する場合(=間隔内で再送禁止)はFalse。

	Raises:
		ValueError: `interval`が0以下の場合。
	"""
	validate_ttl(interval, "interval")
	return bool(
		await client.set(
			key("emailverify_sent", prefix, user_id), str(datetime.now(UTC).timestamp()), nx=True, ex=interval
		)
	)


async def get_login_failure_count(client: Redis, prefix: str, identifier: str, client_ip: str) -> int:
	"""ログイン識別子とIPの組み合わせに対する現在の失敗回数を取得する。

	`login_fail:{identifier_hash}`キーの値を取得する(読み取りのみ、副作用なし)。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		identifier: ログイン識別子。
		client_ip: クライアントのIPアドレス。

	Returns:
		現在の失敗回数。キーが存在しない場合は0。
	"""
	value = await client.get(key("login_fail", prefix, identifier_hash(identifier, client_ip)))
	return int(value) if value is not None else 0


async def get_login_failure_ttl(client: Redis, prefix: str, identifier: str, client_ip: str) -> int:
	"""ログイン失敗カウンタの残りTTL(秒)を取得する。

	`login_fail:{identifier_hash}`キーのTTLを取得する(読み取りのみ、副作用なし)。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		identifier: ログイン識別子。
		client_ip: クライアントのIPアドレス。

	Returns:
		残りTTL(秒)。キーが存在しない場合は`-2`、TTL未設定の場合は`-1`
		(RedisのTTLコマンドの仕様に準じる)。
	"""
	return cast(int, await client.ttl(key("login_fail", prefix, identifier_hash(identifier, client_ip))))


async def incr_login_failure(client: Redis, prefix: str, identifier: str, client_ip: str, window: int) -> int:
	"""ログイン失敗回数を1増加させる。

	`login_fail:{identifier_hash}`キーをインクリメントする副作用を持つ。
	インクリメント後の値が1(=キーが新規作成された)の場合のみ、`window`秒のTTLを
	設定する。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		identifier: ログイン識別子。
		client_ip: クライアントのIPアドレス。
		window: 失敗回数を集計する時間枠(秒)。新規カウント開始時のTTLとして使用する。

	Returns:
		インクリメント後の失敗回数。

	Raises:
		ValueError: `window`が0以下の場合。
	"""
	validate_ttl(window, "window")
	login_key = key("login_fail", prefix, identifier_hash(identifier, client_ip))
	count = int(await client.incr(login_key))
	if count == 1:
		await client.expire(login_key, window)
	return count


async def reset_login_failure(client: Redis, prefix: str, identifier: str, client_ip: str) -> None:
	"""ログイン失敗カウンタをリセットする(ログイン成功時等)。

	`login_fail:{identifier_hash}`キーを削除する副作用を持つ。キーが既に存在しない
	場合もエラーにはならない。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		identifier: ログイン識別子。
		client_ip: クライアントのIPアドレス。

	Returns:
		None。
	"""
	await client.delete(key("login_fail", prefix, identifier_hash(identifier, client_ip)))


async def check_rate_limit(client: Redis, prefix: str, scope: str, value: str, max_requests: int, window: int) -> int:
	"""汎用のレート制限カウンタをインクリメントし、現在のリクエスト数を返す。

	`rate_limit:{scope}:{value_hash}`キーをインクリメントする副作用を持つ。
	インクリメント後の値が1(=キーが新規作成された)の場合のみ、`window`秒のTTLを
	設定する。制限超過の判定(`count > max_requests`)は呼び出し元の責務であり、
	本関数自体は制限を強制しない。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		scope: レート制限の対象範囲を示す識別子。
		value: 制限対象の値(IPアドレス等)。
		max_requests: 許容する最大リクエスト数(呼び出し元が判定に使用する上限値)。
		window: リクエスト数を集計する時間枠(秒)。新規カウント開始時のTTLとして使用する。

	Returns:
		インクリメント後のリクエスト数。

	Raises:
		ValueError: `max_requests`が0以下、または`window`が0以下の場合。
	"""
	if max_requests <= 0:
		raise ValueError("max_requests must be positive")
	validate_ttl(window, "window")
	rate_key = rate_limit_key(scope, value, prefix)
	count = int(await client.incr(rate_key))
	if count == 1:
		await client.expire(rate_key, window)
	return count


async def get_rate_limit_ttl(client: Redis, prefix: str, scope: str, value: str) -> int:
	"""レート制限カウンタの残りTTLを秒単位(切り上げ)で取得する。

	`rate_limit:{scope}:{value_hash}`キーのPTTL(ミリ秒単位の残りTTL)を取得する
	(読み取りのみ、副作用なし)。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		scope: レート制限の対象範囲を示す識別子。
		value: 制限対象の値。

	Returns:
		残りTTL(秒、切り上げ)。キーが存在しない、または既に失効済み(PTTL<=0)の場合は
		`0`を返し、判定(Retry-Afterのフォールバック等)は呼び出し元(`deps.py`)に委ねる。
	"""
	milliseconds = int(await client.pttl(rate_limit_key(scope, value, prefix)))
	if milliseconds <= 0:
		return 0
	return max(1, (milliseconds + 999) // 1000)

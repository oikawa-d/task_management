"""リフレッシュトークン・OAuth state/handoff・パスワードリセット/メール確認トークンの
Redis永続化を扱うデータアクセス層。

読み書きするRedisキーは主に`{prefix}refresh:{token_hash}`(リフレッシュトークン本体)、
`{prefix}user_refresh:{user_id}`(ユーザーが保持するトークンハッシュのSet)、
`{prefix}refresh_used:{old_hash}`・`{prefix}refresh_family_revoked:{user_id}:{family_id}`
(トークン再利用検知用)、`{prefix}oauth_state:{state}`・`{prefix}oauth_handoff:{code}`
(OAuthフロー一時データ)、`{prefix}pwreset*`・`{prefix}emailverify*`
(パスワードリセット/メール確認トークンとその現行トークン参照)。
複数キーにまたがる更新はRedisパイプラインまたはLuaスクリプト(EVAL)による原子的実行で
一貫性を保つ。各関数はRedisコマンドの実行のみを行い、DBのようなトランザクションの
commit/rollbackという概念は持たない。
"""

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

# リフレッシュトークンのローテーションを原子的に行うLuaスクリプト。
# 旧トークンが有効なら新トークンへ差し替え、既に使用済み(再利用)であればトークン
# ファミリー全体を無効化フラグ付きで失効させる(rotate_refresh_token関数で使用)。
_ROTATE_REFRESH_SCRIPT = (Path(__file__).parent / "redis_scripts" / "rotate_refresh_token.lua").read_text(
	encoding="utf-8"
)

# パスワードリセットトークンの新規発行を原子的に行うLuaスクリプト。
# 現在有効なトークンハッシュ(存在すれば)と一致する場合のみ新トークンへ差し替え、
# 一致しない場合は発行を拒否する(save_password_reset_token関数で使用)。
_SAVE_PASSWORD_RESET_SCRIPT = """
local current_hash = redis.call('GET', KEYS[1])
if ARGV[1] == '' then
    if current_hash then return 0 end
elseif current_hash ~= ARGV[1] then
    return 0
end
if current_hash then
    redis.call('DEL', ARGV[5] .. 'pwreset:' .. current_hash)
end
redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[4])
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[4])
return 1
"""

# パスワードリセットトークンの消費(1回限りの使用)を原子的に行うLuaスクリプト。
# トークンが現行トークンと一致する場合のみユーザーIDを返して削除し、消費済みマーカーを
# 残す(consume_password_reset_token関数で使用)。
_CONSUME_PASSWORD_RESET_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if not value then return '' end
local data = cjson.decode(value)
local current_key = ARGV[1] .. 'pwreset_current:' .. data.user_id
if redis.call('GET', current_key) ~= ARGV[2] then return '' end
redis.call('DEL', KEYS[1], current_key)
redis.call('SET', ARGV[1] .. 'pwreset_consumed:' .. data.user_id, ARGV[2], 'EX', ARGV[3])
return data.user_id
"""

# パスワードリセットトークンの復元(メール再送等での巻き戻し)を原子的に行うLuaスクリプト。
# 消費済みマーカーと一致し、かつ現行トークン・新トークンのキーがまだ存在しない場合のみ
# 復元する(restore_password_reset_token関数で使用)。
_RESTORE_PASSWORD_RESET_SCRIPT = """
if redis.call('GET', KEYS[3]) ~= ARGV[1] then return 0 end
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
if redis.call('EXISTS', KEYS[2]) == 1 then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
return 1
"""

# メール確認トークンの復元を原子的に行うLuaスクリプト。
# 現行トークンが未設定、または復元対象と一致する場合のみ復元する
# (restore_email_verify_token関数で使用)。
_RESTORE_EMAIL_VERIFY_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if current and current ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
return 1
"""


async def store_refresh_token(client: Redis, prefix: str, token: str, user_id: UUID, family_id: str, ttl: int) -> None:
	"""リフレッシュトークンを新規保存する。

	トークンをハッシュ化した値をキーとして`refresh:{token_hash}`にTTL付きで保存し、
	`user_refresh:{user_id}`(Set)にトークンハッシュを追加してTTLを設定する副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 保存する生のリフレッシュトークン文字列(ハッシュ化して保存する)。
		user_id: トークンの所有者となるユーザーID。
		family_id: トークンローテーションの系列を識別するID。
		ttl: 有効期限(秒)。

	Returns:
		None。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
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
	"""リフレッシュトークンの情報を取得する。

	トークンをハッシュ化した値で`refresh:{token_hash}`キーを取得する
	(読み取りのみ、副作用なし)。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 検索対象の生のリフレッシュトークン文字列。

	Returns:
		該当するRefreshData。キーが存在しない(未発行・期限切れ・ローテーション済み)
		場合はNone。
	"""
	data = parse_json(await cast(Any, client.get)(key("refresh", prefix, token_hash(token))))
	if data is None:
		return None
	return RefreshData(UUID(str(data["user_id"])), parse_datetime(data["issued_at"]), str(data["family_id"]))


async def rotate_refresh_token(
	client: Redis, prefix: str, old_token: str, new_token: str, ttl: int
) -> RefreshData | TokenReused | None:
	"""リフレッシュトークンをローテーション(旧トークンを新トークンへ差し替え)する。

	`_ROTATE_REFRESH_SCRIPT`(Lua/EVAL)を実行し、`refresh:{old_hash}`を削除して
	`refresh:{new_hash}`を新規作成し、`refresh_used:{old_hash}`に使用済みマーカーを
	残し、`user_refresh:{user_id}`(Set)のトークンハッシュを差し替える副作用を持つ。
	既に失効済みのトークンファミリーに対する再利用が検知された場合は、
	`refresh_family_revoked:{user_id}:{family_id}`に失効フラグを立てる。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		old_token: ローテーション元の生のリフレッシュトークン文字列。
		new_token: ローテーション先の生のリフレッシュトークン文字列。
		ttl: 新トークンの有効期限(秒)。

	Returns:
		ローテーション成功時はRefreshData(新トークンの情報)。
		既に使用済み(再利用)のトークンだった場合はTokenReused。
		`old_token`が存在せず、かつ使用済みマーカーも無い場合はNone。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
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
	"""リフレッシュトークンを1件失効させる。

	`refresh:{token_hash}`を削除し、`user_refresh:{user_id}`(Set)から該当ハッシュを
	取り除く副作用を持つ。対象キーが既に存在しない場合もエラーにはならない。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 失効させる生のリフレッシュトークン文字列。
		user_id: トークンの所有者のユーザーID。

	Returns:
		None。
	"""
	token_hash_value = token_hash(token)
	pipe = client.pipeline(transaction=True)
	pipe.delete(key("refresh", prefix, token_hash_value))
	pipe.srem(key("user_refresh", prefix, user_id), token_hash_value)
	await pipe.execute()


async def revoke_token_family(client: Redis, prefix: str, user_id: UUID, family_id: str, ttl: int | None = None) -> int:
	"""指定ユーザーの特定トークンファミリー(ローテーション系列)を一括失効させる。

	トークン再利用検知時などに使用する。`user_refresh:{user_id}`(Set)配下のトークン
	ハッシュのうち、`family_id`が一致するものについて`refresh:{token_hash}`を削除して
	Setから取り除き、`refresh_family_revoked:{user_id}:{family_id}`に失効フラグを
	TTL付きで立てる副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		user_id: 対象のユーザーID。
		family_id: 失効させるトークンファミリーのID。
		ttl: 失効フラグの有効期限(秒)。指定しない場合は
			`get_backend_settings().refresh_ttl_seconds`を用いる。

	Returns:
		失効させたトークンの件数(該当が無い場合は0)。

	Raises:
		ValueError: 解決後の`ttl`が0以下の場合。
	"""
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
	"""指定ユーザーの全リフレッシュトークンを失効させる(全端末ログアウト等)。

	`user_refresh:{user_id}`(Set)配下の全トークンハッシュについて`refresh:{token_hash}`
	を削除し、`user_refresh:{user_id}`自体も削除する副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		user_id: 対象のユーザーID。

	Returns:
		失効させたトークンの件数(該当が無い場合は0)。
	"""
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
	"""OAuth認可フロー開始時のstate検証用データを保存する。

	`oauth_state:{state}`にTTL付きで新規保存する副作用を持つ(CSRF対策のstateパラメータ
	とPKCE用code_verifier・nonceを紐づけて一時保持する)。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		state: OAuth認可リクエストのstateパラメータ。
		redirect_to: 認可完了後のリダイレクト先。
		code_verifier: PKCE用のcode_verifier。
		nonce: リプレイ攻撃対策用のnonce。
		ttl: 有効期限(秒)。

	Returns:
		None。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
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
	"""OAuth state検証用データを取得し、同時に削除する(1回限りの使用)。

	`GETDEL`により`oauth_state:{state}`を取得し即座に削除する副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		state: 検証対象のstateパラメータ。

	Returns:
		該当するOAuthStateData。キーが存在しない(未発行・期限切れ・使用済み)場合はNone。
	"""
	data = parse_json(await client.getdel(key("oauth_state", prefix, state)))
	if data is None:
		return None
	return OAuthStateData(
		str(data["redirect_to"]), str(data["code_verifier"]), str(data["nonce"]), parse_datetime(data["created_at"])
	)


async def save_oauth_handoff(client: Redis, prefix: str, code: str, user_id: UUID, redirect_to: str, ttl: int) -> None:
	"""OAuthログイン完了後、フロントエンドへ引き渡すための一時データを保存する。

	`oauth_handoff:{code}`にTTL付きで新規保存する副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		code: 引き渡し用のワンタイムコード。
		user_id: ログインが完了したユーザーID。
		redirect_to: 引き渡し完了後のリダイレクト先。
		ttl: 有効期限(秒)。

	Returns:
		None。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
	validate_ttl(ttl)
	await client.setex(
		key("oauth_handoff", prefix, code),
		ttl,
		dump({"user_id": user_id, "redirect_to": redirect_to, "created_at": datetime.now(UTC).isoformat()}),
	)


async def consume_oauth_handoff(client: Redis, prefix: str, code: str) -> OAuthHandoffData | None:
	"""OAuthログイン引き渡し用データを取得し、同時に削除する(1回限りの使用)。

	`GETDEL`により`oauth_handoff:{code}`を取得し即座に削除する副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		code: 検証対象のワンタイムコード。

	Returns:
		該当するOAuthHandoffData。キーが存在しない(未発行・期限切れ・使用済み)場合はNone。
	"""
	data = parse_json(await client.getdel(key("oauth_handoff", prefix, code)))
	if data is None:
		return None
	return OAuthHandoffData(UUID(str(data["user_id"])), str(data["redirect_to"]), parse_datetime(data["created_at"]))


async def save_password_reset_token(client: Redis, prefix: str, token: str, user_id: UUID, ttl: int) -> bool:
	"""パスワードリセットトークンを新規発行する。

	`_SAVE_PASSWORD_RESET_SCRIPT`(Lua/EVAL)を実行し、`pwreset_current:{user_id}`
	(現行トークンハッシュ参照)と`pwreset:{token_hash}`(トークン本体)をそれぞれTTL付きで
	更新する副作用を持つ。既存の現行トークンがあれば削除して差し替える。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 発行する生のパスワードリセットトークン文字列。
		user_id: リセット対象のユーザーID。
		ttl: 有効期限(秒)。

	Returns:
		発行できた場合はTrue。並行リクエスト等により現行トークンの状態が変化していて
		発行に失敗した場合はFalse。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
	validate_ttl(ttl)
	token_hash_value = token_hash(token)
	current_key = key("pwreset_current", prefix, user_id)
	old_hash = await cast(Any, client.get)(current_key) or ""
	result = await cast(Any, client.eval)(
		_SAVE_PASSWORD_RESET_SCRIPT,
		2,
		current_key,
		key("pwreset", prefix, token_hash_value),
		old_hash,
		token_hash_value,
		dump({"user_id": user_id, "requested_at": datetime.now(UTC).isoformat()}),
		ttl,
		prefix,
	)
	return bool(int(result))


async def consume_password_reset_token(client: Redis, prefix: str, token: str) -> UUID | None:
	"""パスワードリセットトークンを消費する(1回限りの使用)。

	`_CONSUME_PASSWORD_RESET_SCRIPT`(Lua/EVAL)を実行し、`pwreset:{token_hash}`と
	`pwreset_current:{user_id}`を削除し、`pwreset_consumed:{user_id}`に消費済み
	マーカーをTTL付きで残す副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 消費する生のパスワードリセットトークン文字列。

	Returns:
		トークンに紐づくユーザーID。トークンが存在しない、または現行トークンと
		一致しない(既に別トークンへ差し替え済み等)場合はNone。

	Raises:
		ValueError: 解決後の`password_reset_ttl_seconds`が0以下の場合。
	"""
	token_hash_value = token_hash(token)
	ttl = get_backend_settings().password_reset_ttl_seconds
	validate_ttl(ttl, "password_reset_ttl_seconds")
	result = await cast(Any, client.eval)(
		_CONSUME_PASSWORD_RESET_SCRIPT,
		1,
		key("pwreset", prefix, token_hash_value),
		prefix,
		token_hash_value,
		ttl,
	)
	if not result:
		return None
	return UUID(str(result.decode() if isinstance(result, bytes) else result))


async def restore_password_reset_token(client: Redis, prefix: str, token: str, user_id: UUID, ttl: int) -> bool:
	"""消費済みのパスワードリセットトークンを復元する(メール誤送信時の巻き戻し等)。

	`_RESTORE_PASSWORD_RESET_SCRIPT`(Lua/EVAL)を実行し、`pwreset_current:{user_id}`と
	`pwreset:{token_hash}`をTTL付きで再作成する副作用を持つ。復元対象が消費済み
	マーカーと一致し、かつ現行・本体キーがまだ存在しない場合のみ復元する。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 復元する生のパスワードリセットトークン文字列。
		user_id: 対象のユーザーID。
		ttl: 有効期限(秒)。

	Returns:
		復元できた場合はTrue。消費済みマーカーと一致しない、または既に別トークンが
		発行済みの場合はFalse。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
	validate_ttl(ttl)
	token_hash_value = token_hash(token)
	result = await cast(Any, client.eval)(
		_RESTORE_PASSWORD_RESET_SCRIPT,
		3,
		key("pwreset_current", prefix, user_id),
		key("pwreset", prefix, token_hash_value),
		key("pwreset_consumed", prefix, user_id),
		token_hash_value,
		dump({"user_id": user_id, "requested_at": datetime.now(UTC).isoformat()}),
		ttl,
	)
	return bool(int(result))


async def replace_email_verify_token(client: Redis, prefix: str, token: str, user_id: UUID, ttl: int) -> None:
	"""メール確認トークンを新規発行し、既存のトークンを差し替える。

	既存の現行トークンハッシュ(`emailverify_current:{user_id}`)があれば
	`emailverify:{old_hash}`を削除したうえで、`emailverify:{token_hash}`
	(トークン本体)と`emailverify_current:{user_id}`(現行トークン参照)をそれぞれ
	TTL付きで更新する副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 発行する生のメール確認トークン文字列。
		user_id: 確認対象のユーザーID。
		ttl: 有効期限(秒)。

	Returns:
		None。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
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
	"""メール確認トークンを消費する(1回限りの使用)。

	`GETDEL`により`emailverify:{token_hash}`を取得し即座に削除する副作用を持つ。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 消費する生のメール確認トークン文字列。

	Returns:
		トークンに紐づくユーザーID。トークンが存在しない(未発行・期限切れ・使用済み)
		場合はNone。
	"""
	data = parse_json(await client.getdel(key("emailverify", prefix, token_hash(token))))
	return UUID(str(data["user_id"])) if data else None


async def restore_email_verify_token(client: Redis, prefix: str, token: str, user_id: UUID, ttl: int) -> bool:
	"""消費済みのメール確認トークンを復元する(メール誤送信時の巻き戻し等)。

	`_RESTORE_EMAIL_VERIFY_SCRIPT`(Lua/EVAL)を実行し、`emailverify:{token_hash}`と
	`emailverify_current:{user_id}`をTTL付きで再作成する副作用を持つ。現行トークンが
	未設定、または復元対象と一致する場合のみ復元する。

	Args:
		client: 使用するRedisクライアント。
		prefix: Redisキープレフィックス。
		token: 復元する生のメール確認トークン文字列。
		user_id: 対象のユーザーID。
		ttl: 有効期限(秒)。

	Returns:
		復元できた場合はTrue。現行トークンが既に別のトークンへ差し替わっている場合はFalse。

	Raises:
		ValueError: `ttl`が0以下の場合。
	"""
	validate_ttl(ttl)
	token_hash_value = token_hash(token)
	result = await cast(Any, client.eval)(
		_RESTORE_EMAIL_VERIFY_SCRIPT,
		2,
		key("emailverify_current", prefix, user_id),
		key("emailverify", prefix, token_hash_value),
		token_hash_value,
		dump({"user_id": user_id, "requested_at": datetime.now(UTC).isoformat()}),
		ttl,
	)
	return bool(int(result))

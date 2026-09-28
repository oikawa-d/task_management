"""app.repository.redis_store（セッション・CSRF・リフレッシュトークン・OAuth state/handoff・
パスワードリセット/メール確認トークン・ログイン失敗カウント・レート制限）に対する単体テスト。
実Redisには接続せず、インメモリの_FakeRedisで代替する。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.repository import redis_store


class _Pipeline:
	"""_FakeRedis.pipeline()が返す、コマンドを溜めてexecute()時に一括反映する疑似パイプライン。"""

	def __init__(self, redis: "_FakeRedis") -> None:
		"""操作対象の_FakeRedisと、実行待ちの操作リストを初期化する。"""
		self.redis = redis
		self.operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

	def __enter__(self) -> "_Pipeline":
		"""redis-pyのwith構文に合わせて自身を返す。"""
		return self

	def __exit__(self, *_args: object) -> None:
		"""特別な後処理は行わない（例外の抑制もしない）。"""
		return None

	def _add(self, name: str, *args: Any, **kwargs: Any) -> "_Pipeline":
		"""呼び出されたコマンド名と引数を実行待ちリストへ積み、メソッドチェーンのため自身を返す。"""
		self.operations.append((name, args, kwargs))
		return self

	def set(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		"""setコマンドを実行待ちリストへ積む。"""
		return self._add("set", *args, **kwargs)

	def setex(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		"""setexコマンドを実行待ちリストへ積む。"""
		return self._add("setex", *args, **kwargs)

	def sadd(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		"""saddコマンドを実行待ちリストへ積む。"""
		return self._add("sadd", *args, **kwargs)

	def srem(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		"""sremコマンドを実行待ちリストへ積む。"""
		return self._add("srem", *args, **kwargs)

	def expire(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		"""expireコマンドを実行待ちリストへ積む。"""
		return self._add("expire", *args, **kwargs)

	def delete(self, *args: Any, **kwargs: Any) -> "_Pipeline":
		"""deleteコマンドを実行待ちリストへ積む。"""
		return self._add("delete", *args, **kwargs)

	async def execute(self) -> list[Any]:
		"""積んだコマンドを登録順に_FakeRedis本体へ適用し、各コマンドの戻り値のリストを返す。"""
		results = []
		for name, args, kwargs in self.operations:
			results.append(await getattr(self.redis, name)(*args, **kwargs))
		return results


class _FakeRedis:
	"""redis_storeが要求するコマンド群をインメモリ辞書で模擬するテスト専用の疑似Redisクライアント。"""

	def __init__(self) -> None:
		"""文字列値・セット・TTLを保持する内部ストレージを初期化する。"""
		self.values: dict[str, str] = {}
		self.sets: dict[str, set[str]] = {}
		self.ttls: dict[str, int] = {}
		self.binary_members = False

	def pipeline(self, transaction: bool = True) -> _Pipeline:
		"""疑似パイプラインを返す（transaction=Falseは想定していないためassertする）。"""
		assert transaction
		return _Pipeline(self)

	async def set(self, name: str, value: str, ex: int | None = None, nx: bool = False) -> bool | None:
		"""キーへ値を設定する。nx=Trueで既存キーがある場合は設定せずNoneを返す（SET NXを模擬）。"""
		if nx and name in self.values:
			return None
		self.values[name] = value
		if ex is not None:
			self.ttls[name] = ex
		return True

	async def setex(self, name: str, time: int, value: str) -> bool:
		"""キーへ値とTTLを同時に設定する（SETEXを模擬）。"""
		self.values[name] = value
		self.ttls[name] = time
		return True

	async def get(self, name: str) -> str | None:
		"""キーの値を取得する。存在しなければNoneを返す。"""
		return self.values.get(name)

	async def getdel(self, name: str) -> str | None:
		"""キーの値を取得すると同時に削除する（GETDELを模擬。一度きりのトークン消費に使う）。"""
		return self.values.pop(name, None)

	async def delete(self, *names: str) -> int:
		"""指定した複数キーの値・セット・TTLをまとめて削除し、実際に削除できた値の件数を返す。"""
		deleted = 0
		for name in names:
			if name in self.values:
				del self.values[name]
				deleted += 1
			self.sets.pop(name, None)
			self.ttls.pop(name, None)
		return deleted

	async def sadd(self, name: str, *values: str) -> int:
		"""セットへメンバーを追加し、新規に追加された件数を返す。"""
		members = self.sets.setdefault(name, set())
		before = len(members)
		members.update(values)
		return len(members) - before

	async def srem(self, name: str, *values: str) -> int:
		"""セットからメンバーを削除し、実際に削除された件数を返す。"""
		members = self.sets.setdefault(name, set())
		removed = sum(value in members for value in values)
		members.difference_update(values)
		return removed

	async def smembers(self, name: str) -> set[str]:
		"""セットの全メンバーを返す。binary_members=Trueの場合はredis-pyのバイナリ応答を模擬してbytesで返す。"""
		members = self.sets.get(name, set())
		return {member.encode() if self.binary_members else member for member in members}  # type: ignore[return-value]

	async def expire(self, name: str, time: int) -> bool:
		"""キーのTTLを設定する。"""
		self.ttls[name] = time
		return True

	async def incr(self, name: str) -> int:
		"""キーの値を整数として1加算する（存在しない場合は0から開始）。"""
		value = int(self.values.get(name, "0")) + 1
		self.values[name] = str(value)
		return value

	async def ttl(self, name: str) -> int:
		"""キーの残りTTL秒を返す（未設定は-1）。"""
		return self.ttls.get(name, -1)

	async def pttl(self, name: str) -> int:
		"""キーの残りTTLミリ秒を返す（未設定は-1000）。"""
		return self.ttls.get(name, -1) * 1000

	async def eval(self, *_args: Any, **_kwargs: Any) -> list[Any]:
		"""Luaスクリプト実行の既定スタブ。個々のテストでAsyncMockに差し替えて戻り値を制御する。"""
		return []

	async def ping(self) -> bool:
		"""疎通確認の既定スタブ。常にTrueを返す。"""
		return True


@pytest.fixture
def redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
	"""redis_store.get_redis_clientと_key_prefixを差し替え、テスト全体で_FakeRedisを使わせるfixture。
	後片付け（キャッシュ等の永続的な状態）は無く、テスト関数ごとに新しい_FakeRedisが使われる。
	"""
	fake = _FakeRedis()
	monkeypatch.setattr(redis_store, "get_redis_client", lambda: fake)
	monkeypatch.setattr(redis_store, "_key_prefix", lambda: "test:")
	return fake


async def test_session_lifecycle_keeps_keys_and_user_set_consistent(redis: _FakeRedis) -> None:
	"""create_sessionでセッション本体・CSRFトークン・ユーザー別セッション集合の3種のキーが整合して作られ、
	get_session/get_csrf_tokenで読み出せること、delete_sessionでセッション本体が削除されると同時に
	ユーザー別セッション集合からも当該セッションIDが取り除かれることを検証する。
	"""
	user_id = uuid.uuid4()
	session_id, csrf_token = await redis_store.create_session(user_id, "127.0.0.1", 60)

	assert json.loads(redis.values[f"test:session:{session_id}"])["user_id"] == str(user_id)
	assert json.loads(redis.values[f"test:csrf:{session_id}"]) == {"token": csrf_token}
	assert session_id in redis.sets[f"test:user_sessions:{user_id}"]
	assert await redis_store.get_session(session_id)
	assert await redis_store.get_csrf_token(session_id) == csrf_token

	assert await redis_store.delete_session(session_id, user_id) is None
	assert await redis_store.get_session(session_id) is None
	assert session_id not in redis.sets[f"test:user_sessions:{user_id}"]


async def test_touch_session_respects_absolute_expiry_and_delete_all(redis: _FakeRedis) -> None:
	"""touch_sessionが、絶対有効期限(absolute_expiry)より前であればTTLを延長してTrueを返すこと、
	絶対有効期限を過ぎている場合はTTLを延長せずFalseを返すことを検証する。
	また delete_all_sessions がユーザーの全セッション数を削除件数として返し、
	ユーザー別セッション集合と各セッションの値をすべて消去することを検証する。
	"""
	user_id = uuid.uuid4()
	first, _ = await redis_store.create_session(user_id, None, 60)
	second, _ = await redis_store.create_session(user_id, None, 60)

	assert await redis_store.touch_session(first, user_id, 30, datetime.now(UTC) + timedelta(seconds=120))
	assert redis.ttls[f"test:session:{first}"] == 30
	assert not await redis_store.touch_session(first, user_id, 30, datetime.now(UTC) - timedelta(seconds=1))
	assert await redis_store.delete_all_sessions(user_id) == 2
	assert not redis.sets.get(f"test:user_sessions:{user_id}")
	assert second not in redis.values


async def test_user_indexes_support_redis_binary_members(redis: _FakeRedis) -> None:
	"""redis-pyがsmembersの結果をバイナリ(bytes)で返す構成であっても、delete_all_sessionsと
	revoke_all_refresh_tokensがメンバー数を正しくデコードして扱い、対象のセッション・
	リフレッシュトークンをすべて削除できることを検証する。
	"""
	user_id = uuid.uuid4()
	first, _ = await redis_store.create_session(user_id, None, 60)
	second, _ = await redis_store.create_session(user_id, None, 60)
	redis.binary_members = True

	assert await redis_store.delete_all_sessions(user_id) == 2
	assert first not in redis.values
	assert second not in redis.values

	await redis_store.store_refresh_token("one", user_id, "family", 90)
	await redis_store.store_refresh_token("two", user_id, "family", 90)
	assert await redis_store.revoke_all_refresh_tokens(user_id) == 2
	assert not [name for name in redis.values if name.startswith("test:refresh:")]


async def test_refresh_token_storage_and_revocation(redis: _FakeRedis) -> None:
	"""store_refresh_tokenで保存したトークンをget_refresh_tokenでuser_id・family_id込みで読み出せること、
	revoke_refresh_tokenで個別トークンを失効できること、revoke_token_familyで同一family_idの
	トークンのみを失効できること、revoke_all_refresh_tokensでユーザーの残り全トークンを
	失効できることを検証する。
	"""
	user_id = uuid.uuid4()
	await redis_store.store_refresh_token("old", user_id, "family", 90)
	data = await redis_store.get_refresh_token("old")

	assert data is not None
	assert data.user_id == user_id
	assert data.family_id == "family"
	assert await redis_store.revoke_refresh_token("old", user_id) is None
	assert await redis_store.get_refresh_token("old") is None

	await redis_store.store_refresh_token("one", user_id, "family", 90)
	await redis_store.store_refresh_token("two", user_id, "other", 90)
	assert await redis_store.revoke_token_family(user_id, "family") == 1
	assert await redis_store.revoke_all_refresh_tokens(user_id) == 1


async def test_one_time_tokens_are_consumed_once(redis: _FakeRedis) -> None:
	"""save_oauth_state/consume_oauth_stateとsave_oauth_handoff/consume_oauth_handoffが、
	いずれも1回目の消費では保存した値（nonceやuser_id）を返し、同じキーでの2回目の消費では
	Noneを返す（GETDELによる使い捨てトークンとして機能する）ことを検証する。
	"""
	user_id = uuid.uuid4()
	await redis_store.save_oauth_state("state", "/dashboard", "verifier", "nonce", 60)
	assert (await redis_store.consume_oauth_state("state")).nonce == "nonce"
	assert await redis_store.consume_oauth_state("state") is None
	await redis_store.save_oauth_handoff("code", user_id, "/dashboard", 60)
	assert (await redis_store.consume_oauth_handoff("code")).user_id == user_id
	assert await redis_store.consume_oauth_handoff("code") is None


async def test_password_and_email_tokens_enforce_current_value(redis: _FakeRedis) -> None:
	"""パスワードリセットトークン・メール確認トークンの保存・消費・復元(restore)系関数について、
	Luaスクリプト(eval)経由の「現在保存されている値と一致する場合のみ許可する」制御に
	従っていること（evalがTrueを返せば成功、Falseを返せば失敗）を検証する。
	またreplace_email_verify_tokenでの再発行後にmark_email_verify_sentが1回目のみTrueを返す
	（連続送信の抑止）こと、consume系が1回消費すると以後はNoneを返すことも合わせて検証する。
	"""
	user_id = uuid.uuid4()
	redis.eval = AsyncMock(return_value=1)
	assert await redis_store.save_password_reset_token("reset", user_id, 60) is True
	assert redis.eval.await_count == 1
	redis.eval = AsyncMock(return_value=0)
	assert await redis_store.save_password_reset_token("reset-lost", user_id, 60) is False
	redis.eval = AsyncMock(return_value=str(user_id))
	assert await redis_store.consume_password_reset_token("reset") == user_id

	await redis_store.replace_email_verify_token("email-one", user_id, 60)
	assert await redis_store.mark_email_verify_sent(user_id, 60)
	assert not await redis_store.mark_email_verify_sent(user_id, 60)
	assert await redis_store.consume_email_verify_token("email-one") == user_id
	assert await redis_store.consume_email_verify_token("email-one") is None
	redis.eval = AsyncMock(return_value=1)
	assert await redis_store.restore_email_verify_token("email-one", user_id, 60) is True
	assert await redis_store.restore_password_reset_token("reset", user_id, 60) is True


async def test_login_failures_and_rate_limit_are_hashed_and_expiring(redis: _FakeRedis) -> None:
	"""ログイン失敗カウント（incr_login_failure/get_login_failure_count/get_login_failure_ttl/
	reset_login_failure）が、識別子の前後空白除去・大文字小文字の正規化を行ったうえで
	同一キーへ集計され、reset後はカウントが0に戻ることを検証する。
	また check_rate_limit がウィンドウ内のリクエスト回数を連番でインクリメントして返し、
	get_rate_limit_ttl が設定したウィンドウ秒数をTTLとして返すことを検証する。
	"""
	assert await redis_store.get_login_failure_count("user@example.com", "127.0.0.1") == 0

	first = await redis_store.incr_login_failure(" User@Example.COM ", "127.0.0.1", 60)
	second = await redis_store.incr_login_failure("user@example.com", "127.0.0.1", 60)
	assert (first, second) == (1, 2)
	assert next(key for key in redis.values if key.startswith("test:login_fail:"))
	assert await redis_store.get_login_failure_count("user@example.com", "127.0.0.1") == 2
	assert await redis_store.get_login_failure_ttl("user@example.com", "127.0.0.1") == 60

	await redis_store.reset_login_failure("user@example.com", "127.0.0.1")
	assert not [key for key in redis.values if key.startswith("test:login_fail:")]
	assert await redis_store.get_login_failure_count("user@example.com", "127.0.0.1") == 0

	assert await redis_store.check_rate_limit("register", "127.0.0.1", 2, 60) == 1
	assert await redis_store.check_rate_limit("register", "127.0.0.1", 2, 60) == 2
	assert await redis_store.check_rate_limit("register", "127.0.0.1", 2, 60) == 3
	assert await redis_store.get_rate_limit_ttl("register", "127.0.0.1") == 60


async def test_rate_limit_ttl_rounds_up_remaining_milliseconds(
	redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""残りTTLがミリ秒単位で端数を持つ場合（1234ms）、get_rate_limit_ttlが秒単位への変換で
	切り捨てず切り上げる（2秒を返す）ことを検証する。
	"""
	monkeypatch.setattr(redis, "pttl", AsyncMock(return_value=1234))

	assert await redis_store.get_rate_limit_ttl("register", "127.0.0.1") == 2


async def test_rate_limit_ttl_returns_zero_when_key_is_missing(
	redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""TTL不明時は`0`を返し、呼び出し側（deps.py）のwindowフォールバックを機能させる。"""
	monkeypatch.setattr(redis, "pttl", AsyncMock(return_value=-2))

	assert await redis_store.get_rate_limit_ttl("register", "127.0.0.1") == 0


async def test_rotate_refresh_token_returns_reuse_marker(redis: _FakeRedis) -> None:
	"""rotate_refresh_tokenの内部で使うLuaスクリプト(eval)がトークン再利用を示す結果
	（[2, user_id, family_id]）を返した場合、戻り値がTokenReused（該当user_id・family_idを保持）と
	なることを検証する。
	"""
	user_id = uuid.uuid4()
	redis.eval = AsyncMock(return_value=[2, str(user_id), "family"])
	result = await redis_store.rotate_refresh_token("old", "new", 60)

	assert isinstance(result, redis_store.TokenReused)
	assert result.user_id == user_id
	assert result.family_id == "family"
	redis.eval.assert_awaited_once()


async def test_ping_propagates_redis_result(redis: _FakeRedis) -> None:
	"""正常時はpingがTrueを返すこと、Redis接続がConnectionErrorを送出する場合はredis_store.pingが
	それを握りつぶさずそのまま伝播させることを検証する。
	"""
	assert await redis_store.ping()
	redis.ping = AsyncMock(side_effect=ConnectionError("down"))
	with pytest.raises(ConnectionError):
		await redis_store.ping()

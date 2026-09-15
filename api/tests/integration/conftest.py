"""Issue #429: 基本認証API（register/login/logout/me/config）の結合テスト共通フィクスチャ。

router→service→repository→実DB/実Redisまでを通しで検証するため、モック済みの
`api/tests/api/routers/test_auth_router.py`（router契約テスト）とは別に、`app.main.app`を
そのままTestClientへ渡し、DB/Redisをモックしない。`apply_migrations`/`db_session`は
`api/tests/conftest.py`のものをそのまま利用する（このファイルでは再定義しない）。

## イベントループに関する注意（重要）

`app.db.get_db_engine()`・`app.redis_client.get_redis_client()`は`lru_cache`によりプロセス内で
使い回されるが、TestClientはリクエストごとに専用ポータル（スレッド）内で非同期処理を実行する。
テスト側で`asyncio.run()`等により別のイベントループから同じキャッシュ済みインスタンスへ
アクセスすると、asyncpg/redis-pyの接続がイベントループを跨いで再利用され
`RuntimeError: ... attached to a different loop`となる。
そのため、本ファイル配下の結合テストでは
- テスト関数自体を`async def`にし（`asyncio_mode = "auto"`）、DB検証は`db_session`
  （テストごとに新規engineを生成する`api/tests/conftest.py`のフィクスチャ）を、
  Redis検証は本ファイルの`redis_conn`（テストごとに新規クライアントを生成）を使う。
- アプリ内部で使われる`get_db_engine()`/`get_redis_client()`はテストコードから直接触らない。

並行作業中の他エージェント（Issue #430/#431）と同一のRedis/PostgreSQLコンテナを共用するため、
flushdb等の破壊的なクリーンアップは行わず、本ファイルが使うキー・ユーザー行のみを個別に削除する。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from app.core.config import get_backend_settings
from app.repository.redis_store_common import rate_limit_key
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ORIGIN = "http://localhost:5173"
# TestClientの既定のclient.hostは"testclient"（IPとして不正な文字列）で、
# login_history.ip_addressがinet型のため、そのままだとDB書き込みでDataErrorになる。
# 本ファイルのTestClientは有効なループバックIPを明示的に使う（下記`client`フィクスチャ参照）。
TEST_CLIENT_IP = "127.0.0.1"
# register結合テストのIP単位レート制限（既定5回/900秒）は本ファイル内で共有・累積するため、
# `_reset_register_rate_limit`でテスト前後にリセットする。
_REGISTER_PASSWORD = "Passw0rd!123"


@pytest.fixture(scope="module")
def client(apply_migrations: None) -> Iterator[TestClient]:
	"""実app・実DB・実Redisを使う結合テスト用クライアント。auth_strategy/DBセッションは一切上書きしない。

	`app.db.get_db_engine()`・`app.redis_client.get_redis_client()`はプロセス内で使い回される
	`lru_cache`済みインスタンスであり、その接続はTestClientの専用ポータル（内部の非同期ループ）に
	紐づく。`client`をテストごとに作り直す（関数スコープにする）と、1つ前のテストのポータルが
	閉じた後も同じキャッシュ済み接続を新しいポータルから使い回そうとして
	`RuntimeError: ... attached to a different loop`になる。そのため`apply_migrations`と同じ
	モジュールスコープにして、1ファイル内では同一のTestClient（＝同一ポータル）を使い回す。
	Cookieの持ち越しは`_clear_client_cookies`（本ファイル）でテストごとに除去する。
	"""
	# `app.main`は初回import時にのみ`configure_logging()`を実行し、root loggerのhandlersを
	# クリアして独自のJSON StreamHandlerへ差し替える。これを何もせず放置すると、同一プロセスで
	# 後続に実行される他モジュールのcaplogベースのテスト（例: test_auth_service.pyのログ検証群）が
	# 壊れるため、import前のhandlers/levelを退避し、本モジュールのテスト終了後に必ず復元する。
	root_logger = logging.getLogger()
	original_handlers = list(root_logger.handlers)
	original_level = root_logger.level

	from app.main import app as main_app

	get_backend_settings.cache_clear()
	try:
		with TestClient(main_app, client=(TEST_CLIENT_IP, 50000)) as test_client:
			# TestClientのポータル内で`redis.asyncio.Redis`の接続プールを初めて使う1回目の呼び出しは、
			# BaseHTTPMiddleware（request_id_middleware）とanyioの組み合わせに起因する既知の
			# イベントループ不整合でRedis呼び出しが失敗することがある（2回目以降は同一ループで成功する）。
			# 実際の検証対象リクエストの前に、無害な/api/healthで一度だけ温めておく。
			test_client.get("/api/health")
			yield test_client
	finally:
		root_logger.handlers = original_handlers
		root_logger.setLevel(original_level)


@pytest.fixture(autouse=True)
def _clear_client_cookies(client: TestClient) -> Iterator[None]:
	"""モジュールスコープで使い回す`client`のCookieが前後のテストへ漏れ出さないようにする。"""
	client.cookies.clear()
	yield
	client.cookies.clear()


@pytest_asyncio.fixture
async def redis_conn() -> AsyncIterator[Redis]:
	"""結合テストの検証・後始末専用の実Redisクライアント（アプリ内部のキャッシュ済みクライアントとは別）。"""
	settings = get_backend_settings()
	client = Redis.from_url(settings.redis_url, decode_responses=True)
	try:
		yield client
	finally:
		await client.aclose()


@pytest_asyncio.fixture(autouse=True)
async def _reset_register_rate_limit(redis_conn: Redis) -> AsyncIterator[None]:
	"""registerのIP単位レート制限キーをテスト前後で削除し、本ファイル内の他テストへ影響させない。"""
	rate_key = rate_limit_key("register", TEST_CLIENT_IP, get_backend_settings().redis_key_prefix)
	await redis_conn.delete(rate_key)
	yield
	await redis_conn.delete(rate_key)


@pytest_asyncio.fixture
async def created_user_ids(db_session: AsyncSession) -> AsyncIterator[list[uuid.UUID]]:
	"""結合テストで作成したusersを終了後に削除する（login_history/oauth_accountsはFKで連鎖処理済み）。"""
	ids: list[uuid.UUID] = []
	yield ids
	if not ids:
		return
	await db_session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids})
	await db_session.commit()


def unique_suffix() -> str:
	return uuid.uuid4().hex[:12]


def register_payload(username: str, email: str, *, password: str = _REGISTER_PASSWORD) -> dict[str, str]:
	return {
		"username": username,
		"email": email,
		"password": password,
		"password_confirm": password,
		"last_name": "山田",
		"first_name": "太郎",
		"last_name_kana": "ヤマダ",
		"first_name_kana": "タロウ",
		"birth_date": "1995-04-01",
	}


async def register_verified_user(
	client: TestClient,
	created_user_ids: list[uuid.UUID],
	db_session: AsyncSession,
	*,
	password: str = _REGISTER_PASSWORD,
) -> dict[str, str]:
	"""register APIで実DBにユーザーを作成し、email_verified_atをDB直接更新で確定させる。

	ログイン結合テストの前提（認証済みユーザー）を、モックではなく実APIの登録結果から作る。
	"""
	from app.repository import user_repository

	suffix = unique_suffix()
	username = f"it{suffix}"
	email = f"{username}@example.com"
	response = client.post(
		"/api/auth/register",
		json=register_payload(username, email, password=password),
		headers={"Origin": ALLOWED_ORIGIN},
	)
	assert response.status_code == 201, response.text
	user_id = uuid.UUID(response.json()["id"])
	created_user_ids.append(user_id)

	await user_repository.mark_email_verified(db_session, user_id)
	await db_session.commit()

	return {"id": str(user_id), "username": username, "email": email, "password": password}

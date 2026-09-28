"""タスクAPI（`/api/tasks`・`/api/projects/{project_id}/tasks`系）結合テスト共通フィクスチャ。

router→service→repository→実DB/実Redisまでを通しで検証するため、`app.main.app`をそのまま
TestClientへ渡し、DB/Redisをモックしない。`scenario`でmember/outsiderの2ユーザーと、
memberが所有するプロジェクト・memberとoutsiderが共有するプロジェクト・outsider単独の
非公開プロジェクト・各種タスクを実DBに作成する。`authenticate`で実ログインしてCookie/JWTを
取得する。テスト終了後は`scenario`が作成したtasks/projects/usersを削除する。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from app.core.config import get_backend_settings
from app.core.security import hash_password
from app.repository import project_member_repository, project_repository, task_repository, user_repository
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ORIGIN = "http://localhost:5173"
PASSWORD = "Passw0rd!123"


@dataclass(frozen=True)
class TaskScenario:
	"""`scenario`フィクスチャが実DBに作成した前提データ（ユーザー・プロジェクト・タスク）の識別子一式。"""

	member_id: uuid.UUID
	outsider_id: uuid.UUID
	member_username: str
	outsider_username: str
	member_project_id: uuid.UUID
	shared_project_id: uuid.UUID
	private_project_id: uuid.UUID
	member_project_task_id: uuid.UUID
	shared_project_task_id: uuid.UUID
	own_unassigned_task_id: uuid.UUID
	outsider_unassigned_task_id: uuid.UUID


@pytest.fixture
def client(apply_migrations: None) -> Iterator[TestClient]:
	"""実app・実DB・実Redisを使う結合テスト用クライアント。

	`apply_migrations`（`api/tests/conftest.py`、実DBへスキーマ適用）に依存し、テストごとに
	キャッシュ済みの認証戦略・DBエンジン・Redisクライアントをクリアしてから起動する。
	TestClientの接続元をINET列（login_history.ip_address）へ書き込める有効なループバックIPに
	固定し、初回リクエストの温め（`/api/health`）を行ってから返す。
	"""
	from app.auth.factory import get_auth_strategy
	from app.db import get_db_engine, get_session_factory
	from app.main import app
	from app.redis_client import get_redis_client

	get_backend_settings.cache_clear()
	get_auth_strategy.cache_clear()
	get_db_engine.cache_clear()
	get_session_factory.cache_clear()
	get_redis_client.cache_clear()
	with TestClient(app) as test_client:
		# PostgreSQLのINET列へ記録できるIPを、TestClientの仮想接続元として使う。
		test_client._transport.client = ("127.0.0.1", 50000)
		test_client.get("/api/health")
		yield test_client
	get_auth_strategy.cache_clear()
	get_db_engine.cache_clear()
	get_session_factory.cache_clear()
	get_redis_client.cache_clear()


@pytest_asyncio.fixture
async def scenario(db_session: AsyncSession) -> Iterator[TaskScenario]:
	"""タスクAPI結合テストの前提データを実DBに作成する。

	member/outsiderの2ユーザー、memberが所有するmember_project（自身のタスク1件付き）、
	outsiderが所有しmemberをメンバー追加したshared_project（outsider作成のタスク1件付き）、
	outsider単独のprivate_project（member非アサインで意図的にタスクは作らない）、
	member/outsiderそれぞれのプロジェクト非アサインタスクを作成する。
	テスト終了後は作成したtasks/projects/usersを削除する。
	"""
	suffix = uuid.uuid4().hex[:12]
	member_id = await user_repository.create(
		db_session, f"member_{suffix}", f"member_{suffix}@example.com", hash_password(PASSWORD)
	)
	outsider_id = await user_repository.create(
		db_session, f"outsider_{suffix}", f"outsider_{suffix}@example.com", hash_password(PASSWORD)
	)
	await user_repository.mark_email_verified(db_session, member_id)
	await user_repository.mark_email_verified(db_session, outsider_id)

	member_project_id = await project_repository.create(db_session, member_id, f"member-{suffix}", None, None, None)
	shared_project_id = await project_repository.create(db_session, outsider_id, f"shared-{suffix}", None, None, None)
	private_project_id = await project_repository.create(db_session, outsider_id, f"private-{suffix}", None, None, None)
	await project_member_repository.create(db_session, shared_project_id, member_id, outsider_id)

	member_project_task_id = await task_repository.create(
		db_session, member_project_id, member_id, None, f"member-task-{suffix}", None, "todo", None, None
	)
	shared_project_task_id = await task_repository.create(
		db_session, shared_project_id, outsider_id, None, f"shared-task-{suffix}", None, "in_progress", None, None
	)
	own_unassigned_task_id = await task_repository.create(
		db_session, None, member_id, None, f"own-unassigned-{suffix}", None, "done", None, None
	)
	outsider_unassigned_task_id = await task_repository.create(
		db_session, None, outsider_id, None, f"outsider-unassigned-{suffix}", None, "todo", None, None
	)
	await db_session.commit()

	value = TaskScenario(
		member_id,
		outsider_id,
		f"member_{suffix}",
		f"outsider_{suffix}",
		member_project_id,
		shared_project_id,
		private_project_id,
		member_project_task_id,
		shared_project_task_id,
		own_unassigned_task_id,
		outsider_unassigned_task_id,
	)
	try:
		yield value
	finally:
		await db_session.execute(
			text("DELETE FROM tasks WHERE created_by = ANY(:ids)"), {"ids": [member_id, outsider_id]}
		)
		await db_session.execute(
			text("DELETE FROM projects WHERE id = ANY(:ids)"),
			{"ids": [member_project_id, shared_project_id, private_project_id]},
		)
		await db_session.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": [member_id, outsider_id]})
		await db_session.commit()


@pytest.fixture
def authenticate(client: TestClient, scenario: TaskScenario):
	"""`scenario`のmember/outsiderで実際に`/api/auth/login`を呼び、後続リクエスト用ヘッダを返す
	関数を提供する。sessionモードは空辞書（Cookieで認証）、jwtモードはAuthorizationヘッダを返す。
	"""

	def _authenticate(user: str = "member") -> dict[str, str]:
		"""`scenario`のmember/outsiderいずれかでログインする。

		Args:
			user: `"member"`または`"member"以外`（outsider扱い）。

		Returns:
			dict[str, str]: 後続リクエストにそのまま付与できる認証ヘッダ（sessionモードでは空辞書）。
		"""
		username = scenario.member_username if user == "member" else scenario.outsider_username
		response = client.post(
			"/api/auth/login",
			json={"identifier": username, "password": PASSWORD},
			headers={"Origin": ALLOWED_ORIGIN},
		)
		if get_backend_settings().auth_mode == "session":
			assert response.status_code == 204, response.text
		else:
			assert response.status_code == 200, response.text
		if get_backend_settings().auth_mode == "jwt":
			return {"Authorization": f"Bearer {response.json()['access_token']}"}
		return {}

	return _authenticate


def write_headers(client: TestClient, auth_headers: dict[str, str]) -> dict[str, str]:
	"""状態変更系リクエスト（POST/PATCH/DELETE）用に、認証ヘッダへOriginと（sessionモードのみ）
	X-CSRF-Tokenを追加する。

	Args:
		client: 結合テスト用TestClient（CSRF Cookie参照に使う）。
		auth_headers: `authenticate`が返した認証ヘッダ。

	Returns:
		dict[str, str]: リクエストにそのまま渡せるヘッダ一式。
	"""
	headers = {**auth_headers, "Origin": ALLOWED_ORIGIN}
	if get_backend_settings().auth_mode == "session":
		headers["X-CSRF-Token"] = client.cookies.get(get_backend_settings().cookie_name_csrf) or ""
	return headers

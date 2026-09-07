import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio

_REQUIRED_ENV_DEFAULTS = {
	"DATABASE_URL": "postgresql+asyncpg://cerberus:cerberus@localhost:5432/cerberus_test",
}

for key, value in _REQUIRED_ENV_DEFAULTS.items():
	os.environ.setdefault(key, value)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
	from app.core.config import get_batch_settings

	get_batch_settings.cache_clear()
	yield
	get_batch_settings.cache_clear()


# batch_historyテーブルのAlembicマイグレーション定義はapi側にのみ存在する（12_table_batch_history.md §4）。
# batchのテスト実行プロセス内でapi/appとbatch/appという同名パッケージを同時にimportすると
# sys.modules上で"app"パッケージが衝突するため、api側のalembicはsubprocess（別プロセス）で
# 実行し、batchテストプロセス自体にはapi側のapp/モジュールを一切importしない設計とする。
_API_DIR = Path(__file__).resolve().parents[2] / "api"
# subprocess実行時のPATHにvenvのbinディレクトリが含まれない場合があるため、
# 現在のPythonインタプリタと同じbinディレクトリにあるalembicを絶対パスで解決する。
_ALEMBIC_EXECUTABLE = str(Path(sys.executable).parent / "alembic")


def _run_alembic(*args: str) -> None:
	result = subprocess.run(
		[_ALEMBIC_EXECUTABLE, *args],
		cwd=str(_API_DIR),
		env=os.environ.copy(),
		capture_output=True,
		text=True,
	)
	if result.returncode != 0:
		raise RuntimeError(f"alembic {' '.join(args)} failed:\nstdout={result.stdout}\nstderr={result.stderr}")


@pytest.fixture(scope="module")
def apply_migrations() -> None:
	_run_alembic("upgrade", "head")
	yield
	_run_alembic("downgrade", "base")


@pytest_asyncio.fixture
async def db_session(apply_migrations: None):
	from app.core.config import get_batch_settings
	from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

	# テスト関数ごとに新しいイベントループで実行されるため、
	# lru_cacheされたapp.db.get_db_engine()を再利用せずテスト専用のengineを都度生成・破棄する。
	engine = create_async_engine(get_batch_settings().database_url)
	session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
	try:
		async with session_factory() as session:
			yield session
			await session.rollback()
	finally:
		await engine.dispose()

import os
from logging.config import fileConfig

from alembic import context
from app.models import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
	# disable_existing_loggers=Falseを明示する。既定(True)だと、alembic.iniにない
	# 既存のロガー（例: pytestプロセス内で先にimportされたapp.*系ロガー）が
	# 無効化(disabled=True)され、以後のプロセス内でログ出力・caplogベースのテストに
	# 影響するため（fileConfigの既知の副作用）。
	fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
	url = os.environ.get("DATABASE_URL")
	if not url:
		raise RuntimeError("DATABASE_URL environment variable is required to run migrations")
	return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


def run_migrations_offline() -> None:
	context.configure(
		url=_database_url(),
		target_metadata=target_metadata,
		literal_binds=True,
		dialect_opts={"paramstyle": "named"},
	)
	with context.begin_transaction():
		context.run_migrations()


def run_migrations_online() -> None:
	configuration = config.get_section(config.config_ini_section) or {}
	configuration["sqlalchemy.url"] = _database_url()
	connectable = engine_from_config(
		configuration,
		prefix="sqlalchemy.",
		poolclass=pool.NullPool,
	)

	with connectable.connect() as connection:
		context.configure(connection=connection, target_metadata=target_metadata)
		with context.begin_transaction():
			context.run_migrations()


if context.is_offline_mode():
	run_migrations_offline()
else:
	run_migrations_online()

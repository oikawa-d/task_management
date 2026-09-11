from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.auth_router import router as auth_router
from app.api.routers.comment_router import router as comment_router
from app.api.routers.notifications_router import router as notifications_router
from app.api.routers.oauth_router import router as oauth_router
from app.api.routers.projects_router import router as projects_router
from app.api.routers.system_router import router as system_router
from app.api.routers.tasks_router import router as tasks_router
from app.core.config import get_backend_settings
from app.core.exceptions import register_error_handling
from app.core.logger import configure_logging
from app.redis_client import close_redis_client, get_redis_client

settings = get_backend_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
	get_redis_client()
	try:
		yield
	finally:
		await close_redis_client()


app = FastAPI(
	title="Cerberus API",
	docs_url="/api/docs" if settings.enable_api_docs else None,
	redoc_url=None,
	lifespan=lifespan,
)

register_error_handling(app)
# allow_credentials=Trueは固定値。CookieベースのDouble Submit Cookie認証（core/deps.pyの
# verify_origin/verify_csrf）を前提としており、settings.cors_allow_originsのワイルドカード
# 禁止バリデータ（core/config.py :: _reject_wildcard_origin）はallow_credentials=Trueである
# ことを前提に成立する（docs/detailed_design/auth/03_csrf.md §10）。
# CORSMiddlewareはミドルウェアスタックの最外周として動作させる必要がある（Starletteは
# 後から追加したミドルウェアほど外側になるため、他のミドルウェアを追加する場合は
# 必ずこのadd_middleware呼び出しより後に追加すること。そうしないとエラーレスポンスに
# CORSヘッダーが付与されない）。
app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.cors_allow_origins,
	allow_credentials=True,
	allow_methods=settings.cors_allow_methods,
	allow_headers=settings.cors_allow_headers,
	max_age=settings.cors_max_age_seconds,
)
app.include_router(system_router)
app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(comment_router)
app.include_router(notifications_router)

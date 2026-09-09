from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.routers.projects_router import router as projects_router
from app.api.routers.system_router import router as system_router
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
app.include_router(system_router)
app.include_router(projects_router)

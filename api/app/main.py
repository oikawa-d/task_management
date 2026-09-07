from fastapi import FastAPI

from app.api.routers.system_router import router as system_router
from app.core.config import get_backend_settings

settings = get_backend_settings()

app = FastAPI(
	title="Cerberus API",
	docs_url="/api/docs" if settings.enable_api_docs else None,
	redoc_url=None,
)

app.include_router(system_router)

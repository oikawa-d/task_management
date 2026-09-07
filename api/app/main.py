from fastapi import FastAPI

from app.api.routers.system_router import router as system_router
from app.core.config import get_backend_settings
from app.core.exceptions import register_error_handling
from app.core.logger import configure_logging

settings = get_backend_settings()
configure_logging(settings.log_level)

app = FastAPI(
	title="Cerberus API",
	docs_url="/api/docs" if settings.enable_api_docs else None,
	redoc_url=None,
)

register_error_handling(app)
app.include_router(system_router)

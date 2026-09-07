from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import BackendSettings, get_backend_settings
from app.db import get_db_engine
from app.redis_client import get_redis_client
from app.schemas.health import HealthResponse
from app.service.health_service import check_health

router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=HealthResponse)
async def get_health(
	response: Response,
	db_engine: AsyncEngine = Depends(get_db_engine),
	redis_client: Redis = Depends(get_redis_client),
	settings: BackendSettings = Depends(get_backend_settings),
) -> HealthResponse:
	health_response, is_healthy = await check_health(db_engine, redis_client, settings)
	response.headers["Cache-Control"] = "no-store"
	response.status_code = 200 if is_healthy else 503
	return health_response

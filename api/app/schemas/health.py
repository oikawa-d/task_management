from typing import Literal

from pydantic import BaseModel


class ComponentHealth(BaseModel):
	status: Literal["ok", "error"]
	latency_ms: int | None = None


class HealthResponse(BaseModel):
	status: Literal["ok", "degraded"]
	auth_mode: str
	components: dict[str, ComponentHealth]

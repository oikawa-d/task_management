from typing import Literal

from pydantic import BaseModel, Field


class ComponentHealth(BaseModel):
	status: Literal["ok", "error"]
	latency_ms: int | None = Field(default=None, ge=0)


class HealthResponse(BaseModel):
	status: Literal["ok", "degraded"]
	auth_mode: Literal["session", "jwt"]
	components: dict[str, ComponentHealth]

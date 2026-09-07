import pytest
from app.schemas.health import ComponentHealth, HealthResponse
from pydantic import ValidationError


def test_health_response_accepts_healthy_components() -> None:
	response = HealthResponse(
		status="ok",
		auth_mode="session",
		components={
			"database": ComponentHealth(status="ok", latency_ms=3),
			"redis": ComponentHealth(status="ok", latency_ms=1),
		},
	)

	assert response.components["database"].latency_ms == 3


def test_health_response_accepts_degraded_component_without_latency() -> None:
	response = HealthResponse(
		status="degraded",
		auth_mode="jwt",
		components={"redis": ComponentHealth(status="error")},
	)

	assert response.components["redis"].latency_ms is None


@pytest.mark.parametrize(
	"schema,field,value",
	[
		(ComponentHealth, "status", "unknown"),
		(ComponentHealth, "latency_ms", -1),
		(HealthResponse, "status", "error"),
		(HealthResponse, "auth_mode", "cookie"),
	],
)
def test_health_schemas_reject_values_outside_design(schema: type, field: str, value: object) -> None:
	kwargs: dict[str, object] = {field: value}
	if schema is HealthResponse:
		kwargs.update(status="ok", auth_mode="session", components={})
		kwargs[field] = value

	with pytest.raises(ValidationError):
		schema(**kwargs)

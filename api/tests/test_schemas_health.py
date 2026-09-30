"""
ヘルスチェックスキーマのコンポーネント状態・遅延時間・ステータスバリデーションを検証するテスト。
"""

import pytest
from app.schemas.health import ComponentHealth, HealthResponse
from pydantic import ValidationError


def test_health_response_accepts_healthy_components() -> None:
	"""
	HealthResponse がすべてのコンポーネントが ok 状態でレイテンシ情報を持つケースを受け入れることを検証。

	条件：database と redis コンポーネントが ok 状態で、それぞれレイテンシ（latency_ms）を持つHealthResponse を作成したとき、コンポーネント情報が正しく保持されること。
	"""
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
	"""
	HealthResponse が status="degraded" で、コンポーネントが error 状態でレイテンシ情報なしのケースを受け入れることを検証。

	条件：redis コンポーネントが error 状態で latency_ms が指定されていないHealthResponse を作成したとき、latency_ms が None に保たれること。
	"""
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
	"""
	ComponentHealth と HealthResponse が設計定義外のステータス・遅延時間値を拒否することを検証。

	条件：ComponentHealth の status="unknown" または latency_ms=-1、HealthResponse の status="error" または auth_mode="cookie" を入力したとき、ValidationError が送出されること。
	"""
	kwargs: dict[str, object] = {field: value}
	if schema is HealthResponse:
		kwargs.update(status="ok", auth_mode="session", components={})
		kwargs[field] = value

	with pytest.raises(ValidationError):
		schema(**kwargs)

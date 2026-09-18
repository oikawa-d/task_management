"""ヘルスチェックエンドポイント（`GET /health`）のレスポンスDTOを定義するモジュール。"""

from typing import Literal

from pydantic import BaseModel, Field


class ComponentHealth(BaseModel):
	"""DB・Redis等、個々の依存コンポーネントの死活状態を表すDTO。`HealthResponse.components` の値として使う。"""

	status: Literal["ok", "error"]
	latency_ms: int | None = Field(default=None, ge=0)


class HealthResponse(BaseModel):
	"""`GET /health` のレスポンスDTO。全体ステータスと稼働中の認証方式、依存コンポーネント別の状態を返す。"""

	status: Literal["ok", "degraded"]
	auth_mode: Literal["session", "jwt"]
	components: dict[str, ComponentHealth]

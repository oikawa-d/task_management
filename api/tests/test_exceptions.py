"""`app.core.exceptions.register_error_handling`によるエラーハンドリング統合のテスト。

アプリ例外（`AppError`系）・未処理例外・Redis/SQLAlchemyのインフラ例外・
バリデーションエラーそれぞれが、共通のエラーレスポンス形式・ステータスコード・
構造化ログへ変換されることを検証する。
"""

import logging
from types import SimpleNamespace
from unittest.mock import patch

import app.core.exceptions as exceptions_module
from app.core.exceptions import (
	ForbiddenError,
	NotFoundError,
	ServiceUnavailableError,
	TooManyAttemptsError,
	register_error_handling,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import DBAPIError, DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


class _Payload(BaseModel):
	"""バリデーションエラーのテスト用に、必須文字列フィールド`name`のみを持つ入力スキーマ。"""

	name: str


def _build_app() -> FastAPI:
	"""`register_error_handling`を適用した上で、各種例外・正常系を意図的に発生させる
	検証用エンドポイント群を持つ`FastAPI`アプリを構築するヘルパー関数。

	Returns:
		FastAPI: `/boom-*`系の例外送出用エンドポイントと`/validate`・`/ok`を含むアプリ。
	"""
	app = FastAPI()
	register_error_handling(app)

	@app.get("/boom-app-error")
	async def boom_app_error() -> None:
		raise NotFoundError()

	@app.get("/boom-forbidden")
	async def boom_forbidden() -> None:
		raise ForbiddenError(message="権限がありません", details={"reason": "role"})

	@app.get("/boom-rate-limit")
	async def boom_rate_limit() -> None:
		raise TooManyAttemptsError(retry_after=42)

	@app.get("/boom-unhandled")
	async def boom_unhandled() -> None:
		raise RuntimeError("unexpected")

	@app.get("/boom-service-unavailable")
	async def boom_service_unavailable() -> None:
		raise ServiceUnavailableError()

	@app.get("/boom-redis-error")
	async def boom_redis_error() -> None:
		raise RedisConnectionError("redis down")

	@app.get("/boom-operational-error")
	async def boom_operational_error() -> None:
		raise OperationalError("SELECT 1", {}, SimpleNamespace(sqlstate="08006"))

	@app.get("/boom-operational-error-pgcode")
	async def boom_operational_error_pgcode() -> None:
		raise OperationalError("SELECT 1", {}, SimpleNamespace(sqlstate=None, pgcode="08006"))

	@app.get("/boom-operational-error-retryable")
	async def boom_operational_error_retryable() -> None:
		raise OperationalError("SELECT 1", {}, SimpleNamespace(sqlstate="57P03"))

	@app.get("/boom-operational-error-no-sqlstate")
	async def boom_operational_error_no_sqlstate() -> None:
		raise OperationalError("SELECT 1", {}, SimpleNamespace())

	@app.get("/boom-dbapi-error")
	async def boom_dbapi_error() -> None:
		raise DBAPIError("SELECT 1", {}, SimpleNamespace(sqlstate="08006"))  # type: ignore[arg-type]

	@app.get("/boom-unknown-operational-error")
	async def boom_unknown_operational_error() -> None:
		raise OperationalError("SELECT 1", {}, SimpleNamespace(sqlstate="40P01"))

	@app.get("/boom-interface-error")
	async def boom_interface_error() -> None:
		raise InterfaceError("SELECT 1", {}, Exception("connection lost"))

	@app.get("/boom-pool-timeout-error")
	async def boom_pool_timeout_error() -> None:
		raise SQLAlchemyTimeoutError("接続プールの取得がタイムアウトしました")

	@app.get("/boom-disconnection-error")
	async def boom_disconnection_error() -> None:
		raise DisconnectionError("connection invalidated")

	@app.post("/validate")
	async def validate(payload: _Payload) -> dict[str, str]:
		return {"name": payload.name}

	@app.get("/ok")
	async def ok() -> dict[str, bool]:
		return {"ok": True}

	return app


def _client() -> TestClient:
	"""検証用アプリに対する`TestClient`を、サーバー側例外をそのまま再送出せず
	HTTPレスポンスとして受け取れる設定（`raise_server_exceptions=False`）で生成するヘルパー関数。

	Returns:
		TestClient: `/boom-*`系エンドポイントを持つ検証用アプリのテストクライアント。
	"""
	return TestClient(_build_app(), raise_server_exceptions=False)


def test_app_error_converted_to_common_error_response() -> None:
	"""`NotFoundError`が404と共通形式のエラーボディ（`code="NOT_FOUND"`・`request_id`）へ
	変換されることを検証する。
	"""
	res = _client().get("/boom-app-error")

	assert res.status_code == 404
	body = res.json()
	assert body["error"]["code"] == "NOT_FOUND"
	assert "request_id" in body["error"]


def test_app_error_with_details() -> None:
	"""`ForbiddenError`に渡した`details`が、403レスポンスのエラーボディへ
	そのまま引き継がれることを検証する。
	"""
	res = _client().get("/boom-forbidden")

	assert res.status_code == 403
	body = res.json()
	assert body["error"]["code"] == "FORBIDDEN"
	assert body["error"]["details"] == {"reason": "role"}


def test_rate_limit_error_includes_retry_after_header() -> None:
	"""`TooManyAttemptsError(retry_after=42)`が429レスポンスへ変換され、
	`Retry-After`ヘッダーに指定秒数がそのまま設定されることを検証する。
	"""
	res = _client().get("/boom-rate-limit")

	assert res.status_code == 429
	assert res.headers["Retry-After"] == "42"


def test_unhandled_exception_converted_to_internal_error() -> None:
	"""アプリ例外体系に属さない`RuntimeError`が500と`code="INTERNAL_ERROR"`、
	利用者向け固定メッセージ「サーバーエラーが発生しました」へ変換されることを検証する。
	"""
	res = _client().get("/boom-unhandled")

	assert res.status_code == 500
	body = res.json()
	assert body["error"]["code"] == "INTERNAL_ERROR"
	assert body["error"]["message"] == "サーバーエラーが発生しました"


def test_unhandled_exception_emits_event_and_request_id() -> None:
	"""未処理例外のハンドラーが、`logger.exception`に`event="unhandled_exception"`と
	レスポンスボディの`request_id`を一致させた`extra`を渡してログ出力することを検証する。
	"""
	with patch.object(exceptions_module.logger, "exception") as log_exception:
		response = _client().get("/boom-unhandled")

	assert log_exception.call_args.kwargs["extra"] == {
		"event": "unhandled_exception",
		"request_id": response.json()["error"]["request_id"],
	}


def _assert_service_unavailable_body(body: dict) -> None:
	"""503レスポンスの共通ボディが、`code="SERVICE_UNAVAILABLE"`・固定の利用者向けメッセージ・
	`details=None`・`request_id`を含む形式であることを検証するアサーションヘルパー関数。

	Args:
		body: 検証対象のレスポンスJSONをパースした辞書。
	"""
	assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
	assert body["error"]["message"] == "現在サービスをご利用いただけません"
	assert body["error"]["details"] is None
	assert "request_id" in body["error"]


def test_service_unavailable_app_error_returns_503() -> None:
	"""`ServiceUnavailableError`が503と共通のサービス利用不可ボディへ変換されることを検証する。"""
	res = _client().get("/boom-service-unavailable")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_503_handlers_emit_common_structured_log_fields() -> None:
	"""アプリ例外由来の503（`ServiceUnavailableError`）とインフラ例外由来の503（Redis接続エラー）の
	両方について、`logger.exception`が`event="service_unavailable"`と各レスポンスの`request_id`を
	一致させた`extra`で1回ずつ呼ばれることを検証する。
	"""
	with patch.object(exceptions_module.logger, "exception") as log_exception:
		app_error_response = _client().get("/boom-service-unavailable")
		infra_error_response = _client().get("/boom-redis-error")

	assert log_exception.call_count == 2
	app_extra = log_exception.call_args_list[0].kwargs["extra"]
	infra_extra = log_exception.call_args_list[1].kwargs["extra"]

	assert app_extra == {
		"event": "service_unavailable",
		"request_id": app_error_response.json()["error"]["request_id"],
	}
	assert infra_extra == {
		"event": "service_unavailable",
		"request_id": infra_error_response.json()["error"]["request_id"],
	}


def test_app_error_handler_does_not_log_client_errors(caplog) -> None:
	"""4xx系のアプリ例外（`NotFoundError`）では、`app.error`ロガーへERRORレベルの
	ログが一切出力されないことを検証する。
	"""
	with caplog.at_level(logging.ERROR, logger="app.error"):
		response = _client().get("/boom-app-error")

	assert response.status_code == 404
	assert not [record for record in caplog.records if record.name == "app.error"]


def test_redis_error_is_converted_to_503_by_infra_error_handler() -> None:
	"""Redisの`ConnectionError`がインフラエラーハンドラーにより503・共通のサービス利用不可ボディへ
	変換されることを検証する。
	"""
	res = _client().get("/boom-redis-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_operational_error_is_converted_to_503_by_infra_error_handler() -> None:
	"""sqlstate="08006"（接続例外）を持つ`OperationalError`が503・共通の
	サービス利用不可ボディへ変換されることを検証する。
	"""
	res = _client().get("/boom-operational-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_operational_error_uses_pgcode_when_sqlstate_is_missing() -> None:
	"""`orig.sqlstate`が無く`orig.pgcode="08006"`のみ持つ`OperationalError`でも、
	pgcodeを接続例外として扱い503へ変換されることを検証する。
	"""
	res = _client().get("/boom-operational-error-pgcode")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_operational_error_with_retryable_sqlstate_is_converted_to_503() -> None:
	"""`_POSTGRES_RETRYABLE_CONNECTION_STATES`に含まれるsqlstate="57P03"を持つ
	`OperationalError`が、接続例外プレフィックス"08"と同様に503へ変換されることを検証する。
	"""
	res = _client().get("/boom-operational-error-retryable")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_operational_error_without_sqlstate_returns_internal_error() -> None:
	"""`orig`に`sqlstate`も`pgcode`も持たない`OperationalError`は接続例外と判定されず、
	500・`code="INTERNAL_ERROR"`になることを検証する。
	"""
	res = _client().get("/boom-operational-error-no-sqlstate")

	assert res.status_code == 500
	assert res.json()["error"]["code"] == "INTERNAL_ERROR"


def test_non_operational_dbapi_error_returns_internal_error() -> None:
	"""`OperationalError`ではない一般の`DBAPIError`は接続例外判定の対象外であり、
	500・`code="INTERNAL_ERROR"`になることを検証する。
	"""
	res = _client().get("/boom-dbapi-error")

	assert res.status_code == 500
	assert res.json()["error"]["code"] == "INTERNAL_ERROR"


def test_operational_error_with_unmapped_sqlstate_returns_internal_error() -> None:
	"""接続例外プレフィックス"08"にもリトライ可能一覧にも該当しないsqlstate="40P01"
	（デッドロック検出）を持つ`OperationalError`は、500・`code="INTERNAL_ERROR"`になることを検証する。
	"""
	res = _client().get("/boom-unknown-operational-error")

	assert res.status_code == 500
	assert res.json()["error"]["code"] == "INTERNAL_ERROR"


def test_unmapped_operational_error_emits_internal_event_and_request_id() -> None:
	"""未マッピングsqlstateの`OperationalError`について、`logger.exception`が
	`event="infrastructure_error"`とレスポンスの`request_id`を一致させた`extra`で
	呼ばれることを検証する。
	"""
	with patch.object(exceptions_module.logger, "exception") as log_exception:
		response = _client().get("/boom-unknown-operational-error")

	assert log_exception.call_args.kwargs["extra"] == {
		"event": "infrastructure_error",
		"request_id": response.json()["error"]["request_id"],
	}


def test_interface_error_is_converted_to_503_by_infra_error_handler() -> None:
	"""`InterfaceError`（DBAPIとの通信断）が503・共通のサービス利用不可ボディへ
	変換されることを検証する。
	"""
	res = _client().get("/boom-interface-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_pool_timeout_error_is_converted_to_503_by_infra_error_handler() -> None:
	"""SQLAlchemyの接続プール取得タイムアウト（`TimeoutError`）が503・共通の
	サービス利用不可ボディへ変換されることを検証する。
	"""
	res = _client().get("/boom-pool-timeout-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_disconnection_error_is_converted_to_503_by_infra_error_handler() -> None:
	"""`DisconnectionError`（コネクション無効化）が503・共通のサービス利用不可ボディへ
	変換されることを検証する。
	"""
	res = _client().get("/boom-disconnection-error")

	assert res.status_code == 503
	_assert_service_unavailable_body(res.json())


def test_validation_error_returns_field_details() -> None:
	"""必須フィールド`name`を欠いたリクエストボディが422・`code="VALIDATION_ERROR"`となり、
	エラー詳細の`field`にフィールド名`name`が含まれることを検証する。
	"""
	res = _client().post("/validate", json={})

	assert res.status_code == 422
	body = res.json()
	assert body["error"]["code"] == "VALIDATION_ERROR"
	assert body["error"]["details"][0]["field"].endswith("name")


def test_response_includes_request_id_header() -> None:
	"""正常応答（`/ok`）にも`X-Request-ID`ヘッダーが付与されることを検証する。"""
	res = _client().get("/ok")

	assert res.status_code == 200
	assert "X-Request-ID" in res.headers

"""API呼び出し履歴（`api_history`）を記録するHTTPミドルウェアを提供するモジュール。

リクエスト/レスポンスボディの機微情報マスキング、エラー内容の抽出、DB保存までを行う。
"""

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response

from app.core.client_ip import resolve_client_ip
from app.core.config import BackendSettings, get_backend_settings
from app.db import get_session_factory
from app.repository import api_history_repository
from app.repository.api_history_repository import ApiHistoryCreateInput

logger = logging.getLogger("app.history")
_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = frozenset(
	{
		"password",
		"password_confirmation",
		"current_password",
		"new_password",
		"password_confirm",
		"token",
		"access_token",
		"refresh_token",
		"client_secret",
		"code",
		"state",
		"csrf_token",
	}
)


def _mask(value: Any) -> Any:
	"""辞書・リストを再帰的に走査し、`_SENSITIVE_KEYS`に該当するキーの値を`[REDACTED]`へ置換する。"""
	if isinstance(value, dict):
		return {
			_key: (_REDACTED if _key.lower() in _SENSITIVE_KEYS else _mask(_value)) for _key, _value in value.items()
		}
	if isinstance(value, list):
		return [_mask(item) for item in value]
	return value


def _safe_body(request: Request, raw_body: bytes, settings: BackendSettings) -> dict[str, object] | None:
	"""リクエストボディを履歴保存用に安全な形へ変換する。

	JSON以外・サイズ超過・パース不能・オブジェクトでない場合はNoneを返し、
	機微フィールドは`_mask`でマスキングしたうえで返す。

	Args:
		request: 対象のHTTPリクエスト。
		raw_body: 読み取り済みの生ボディ。
		settings: `api_history_body_max_bytes`を保持するバックエンド設定。

	Returns:
		マスキング済みのボディ（辞書）、または保存不要と判定した場合はNone。
	"""
	if not raw_body or "application/json" not in request.headers.get("content-type", "").lower():
		return None
	if len(raw_body) > settings.api_history_body_max_bytes:
		return None
	try:
		decoded = json.loads(raw_body)
	except UnicodeError:
		return None
	except json.JSONDecodeError:
		return None
	return _mask(decoded) if isinstance(decoded, dict) else None


def _route_path(request: Request) -> str:
	"""履歴記録用のパスを取得する。ルート定義済みならテンプレート（例: `/api/tasks/{task_id}`）を、
	未解決（404等）なら実際のリクエストパスを返す。"""
	route = request.scope.get("route")
	path = getattr(route, "path", None)
	return path if isinstance(path, str) else request.url.path


async def _read_response_body(response: Response) -> bytes | None:
	"""レスポンスボディを履歴記録のために読み取る。

	ストリーミングレスポンス（`body_iterator`）の場合は一度全チャンクを読み切り、
	クライアントへ再生できるよう`body_iterator`を読み取り済みチャンクで差し替える
	（副作用: `response.body_iterator`を書き換える）。

	Args:
		response: 対象のHTTPレスポンス。

	Returns:
		読み取ったボディ全体。`body`属性・`body_iterator`のいずれも無い場合はNone。
	"""
	body = getattr(response, "body", None)
	if isinstance(body, bytes):
		return body
	iterator = getattr(response, "body_iterator", None)
	if iterator is None:
		return None
	chunks: list[bytes] = []
	async for chunk in iterator:
		chunks.append(chunk.encode() if isinstance(chunk, str) else chunk)

	async def replay() -> Any:
		"""読み取り済みチャンクを、元のasyncイテレータの代わりとしてクライアントへ再生する。"""
		for chunk in chunks:
			yield chunk

	setattr(response, "body_iterator", replay())

	return b"".join(chunks)


def _error_fields(response: Response, body: bytes | None) -> tuple[str | None, str | None]:
	"""エラーレスポンスのJSONボディから`error.code`と`error.message`を抽出する。

	正常系（4xx未満）やパース不能・想定外形式の場合は`(None, None)`を返す。

	Args:
		response: 対象のHTTPレスポンス。
		body: `_read_response_body`で読み取った生ボディ。

	Returns:
		`(error_code, error_message)`のタプル。抽出できない場合は両方None。
	"""
	if response.status_code < 400 or body is None:
		return None, None
	try:
		decoded = json.loads(body)
	except UnicodeError:
		return None, None
	except json.JSONDecodeError:
		return None, None
	if not isinstance(decoded, dict):
		return None, None
	error = decoded.get("error")
	if not isinstance(error, dict):
		return None, None
	code = error.get("code")
	detail = error.get("message")
	return (code if isinstance(code, str) else None, detail if isinstance(detail, str) else None)


async def _save_history(data: ApiHistoryCreateInput) -> None:
	"""API呼び出し履歴をDBへ保存する。保存自体の失敗はAPI応答に影響させず、ログに記録するのみとする。

	Args:
		data: 保存対象の履歴データ（リクエスト/レスポンス情報一式）。
	"""
	try:
		async with get_session_factory()() as db:
			await api_history_repository.create(db, data)
			await db.commit()
	except Exception:
		logger.exception(
			"api history save failed",
			extra={"event": "api_history_write_failed", "request_id": str(data.request_id)},
		)


def register_history_middleware(app: FastAPI) -> None:
	"""`/api`配下へのリクエストごとに、開始から終了までを計測し履歴を記録するミドルウェアを登録する。

	Args:
		app: ミドルウェアを登録するFastAPIアプリケーション。
	"""

	@app.middleware("http")
	async def history_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
		"""1リクエスト分の処理時間・ステータス・エラー内容・マスキング済みボディ等を収集し、
		`_save_history`でDBへ保存したうえでレスポンスを返す。"""
		if not request.url.path.startswith("/api"):
			return await call_next(request)

		settings = get_backend_settings()
		request_id = uuid.uuid4()
		request.state.request_id = str(request_id)
		started = time.perf_counter()
		raw_body = await request.body()

		async def receive() -> dict[str, Any]:
			"""既に読み取り済みの`raw_body`を、後続のリクエストボディ読み取りへ再度供給するASGI receive関数。"""
			return {"type": "http.request", "body": raw_body, "more_body": False}

		request._receive = receive
		response: Response | None = None
		response_body: bytes | None = None
		try:
			response = await call_next(request)
			response_body = await _read_response_body(response)
		finally:
			status_code = response.status_code if response is not None else 500
			error_code, error_detail = (
				_error_fields(response, response_body) if response is not None else ("INTERNAL_ERROR", None)
			)
			if status_code >= 400 and error_code is None and error_detail is None:
				error_code = "HTTP_ERROR"
			client_ip = resolve_client_ip(request, settings.trusted_proxy_cidrs).client_ip
			data = ApiHistoryCreateInput(
				request_id=request_id,
				method=request.method,
				path=_route_path(request),
				status="error" if status_code >= 400 else "success",
				status_code=status_code,
				error_code=error_code,
				error_detail=(error_detail or "")[: settings.api_history_error_detail_max_length] or None,
				body=_safe_body(request, raw_body, settings),
				user_id=getattr(getattr(request.state, "current_user", None), "id", None),
				ip_address=client_ip,
				user_agent=request.headers.get("user-agent"),
				duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
			)
			await _save_history(data)
			if response is not None:
				response.headers.setdefault("X-Request-ID", str(request_id))
			logger.info("api request", extra={"event": "api_request", "request_id": str(request_id)})
		assert response is not None
		return response

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.error")


class AppError(Exception):
	code = "INTERNAL_ERROR"
	status_code = 500
	message = "サーバーエラーが発生しました"

	def __init__(self, message: str | None = None, details: Any = None) -> None:
		super().__init__(message or self.message)
		if message is not None:
			self.message = message
		self.details = details


class NotFoundError(AppError):
	code = "NOT_FOUND"
	status_code = 404
	message = "リソースが見つかりません"


class ForbiddenError(AppError):
	code = "FORBIDDEN"
	status_code = 403
	message = "このリソースへのアクセス権がありません"


class CsrfInvalidError(ForbiddenError):
	code = "CSRF_INVALID"
	message = "CSRFトークンが不正です"


class ConflictError(AppError):
	status_code = 409
	message = "競合が発生しました"


class AlreadyMemberError(ConflictError):
	code = "ALREADY_MEMBER"
	message = "既にプロジェクトのメンバーです"


class OwnerCannotBeRemovedError(ConflictError):
	code = "OWNER_CANNOT_BE_REMOVED"
	message = "オーナーはメンバーから削除できません"


class UnauthenticatedError(AppError):
	code = "UNAUTHENTICATED"
	status_code = 401
	message = "認証が必要です"


class NotSupportedInModeError(AppError):
	code = "NOT_SUPPORTED_IN_MODE"
	status_code = 405
	message = "現在の認証方式ではサポートされていません"


class SessionExpiredError(UnauthenticatedError):
	code = "SESSION_EXPIRED"
	message = "セッションの有効期限が切れました"


class TokenInvalidError(UnauthenticatedError):
	code = "TOKEN_INVALID"
	message = "トークンが正しくありません"


class TokenExpiredError(UnauthenticatedError):
	code = "TOKEN_EXPIRED"
	message = "トークンの有効期限が切れています"


class TokenRevokedError(UnauthenticatedError):
	code = "TOKEN_REVOKED"
	message = "セッションが無効になりました。再度ログインしてください"


class UserInactiveError(AppError):
	code = "USER_INACTIVE"
	status_code = 403
	message = "このアカウントは無効化されています"


def _build_error_body(code: str, message: str, details: Any, request_id: str) -> dict[str, Any]:
	return {
		"error": {
			"code": code,
			"message": message,
			"details": details,
			"request_id": request_id,
		}
	}


def register_error_handling(app: FastAPI) -> None:
	@app.middleware("http")
	async def request_id_middleware(request: Request, call_next: Any) -> Any:
		request_id = str(uuid.uuid4())
		request.state.request_id = request_id
		response = await call_next(request)
		response.headers["X-Request-ID"] = request_id
		return response

	@app.exception_handler(AppError)
	async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		return JSONResponse(
			status_code=exc.status_code,
			content=_build_error_body(exc.code, exc.message, exc.details, request_id),
		)

	@app.exception_handler(RequestValidationError)
	async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		details = [{"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]} for err in exc.errors()]
		return JSONResponse(
			status_code=422,
			content=_build_error_body("VALIDATION_ERROR", "入力内容に誤りがあります", details, request_id),
		)

	@app.exception_handler(Exception)
	async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		logger.exception("unhandled exception", extra={"request_id": request_id})
		return JSONResponse(
			status_code=500,
			content=_build_error_body("INTERNAL_ERROR", "サーバーエラーが発生しました", None, request_id),
		)

import logging
import uuid
from typing import Any, NoReturn

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import DBAPIError, DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

logger = logging.getLogger("app.error")
_POSTGRES_CONNECTION_SQLSTATE_PREFIX = "08"
_POSTGRES_RETRYABLE_CONNECTION_STATES = frozenset({"57P03"})


class AppError(Exception):
	code = "INTERNAL_ERROR"
	status_code = 500
	message = "サーバーエラーが発生しました"
	retry_after: int | None = None

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


class TaskConflictError(ConflictError):
	code = "TASK_CONFLICT"
	message = "他のユーザーが先に更新しました。最新の内容を取得し直してください"


class AssigneeInactiveError(ConflictError):
	code = "ASSIGNEE_INACTIVE"
	message = "無効なユーザーは担当者に指定できません"


class DuplicateUsernameError(ConflictError):
	code = "DUPLICATE_USERNAME"
	message = "このユーザーIDは既に使用されています"


class DuplicateEmailError(ConflictError):
	code = "DUPLICATE_EMAIL"
	message = "このメールアドレスは既に使用されています"


class AlreadyMemberError(ConflictError):
	code = "ALREADY_MEMBER"
	message = "既にプロジェクトのメンバーです"


class OwnerCannotBeRemovedError(ConflictError):
	code = "OWNER_CANNOT_BE_REMOVED"
	message = "オーナーはメンバーから削除できません"


class SelfModificationError(ConflictError):
	code = "SELF_MODIFICATION_NOT_ALLOWED"
	message = "自分自身に対してこの操作は実行できません"


class LastAdminRequiredError(ConflictError):
	code = "LAST_ADMIN_REQUIRED"
	message = "最後の管理者に対してこの操作は実行できません"


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


class InvalidStateError(AppError):
	code = "INVALID_STATE"
	status_code = 400
	message = "OAuth stateが無効です"


class OAuthFailedError(AppError):
	code = "OAUTH_FAILED"
	status_code = 400
	message = "OAuth認証に失敗しました"


class OAuthDisabledError(NotFoundError):
	code = "OAUTH_DISABLED"
	message = "Googleログインは現在無効です"


class OAuthEmailUnverifiedError(AppError):
	code = "OAUTH_EMAIL_UNVERIFIED"
	status_code = 400
	message = "Googleアカウントのメールアドレスが検証されていません"


class OAuthHandoffInvalidError(AppError):
	code = "OAUTH_HANDOFF_INVALID"
	status_code = 400
	message = "OAuthログインの有効期限が切れています"


class UserInactiveError(AppError):
	code = "USER_INACTIVE"
	status_code = 403
	message = "このアカウントは無効化されています"


class EmailNotVerifiedError(AppError):
	code = "EMAIL_NOT_VERIFIED"
	status_code = 403
	message = "メールアドレスの認証が完了していません"


class InvalidCredentialsError(UnauthenticatedError):
	code = "INVALID_CREDENTIALS"
	message = "IDまたはパスワードが正しくありません"


class TooManyAttemptsError(AppError):
	code = "TOO_MANY_ATTEMPTS"
	status_code = 429
	message = "試行回数が多いため、しばらく待ってから再度お試しください"

	def __init__(self, message: str | None = None, details: Any = None, retry_after: int | None = None) -> None:
		super().__init__(message, details)
		self.retry_after = retry_after


class InvalidVerifyTokenError(AppError):
	code = "INVALID_VERIFY_TOKEN"
	status_code = 400
	message = "認証リンクが無効か、有効期限が切れています"


class InvalidResetTokenError(AppError):
	code = "INVALID_RESET_TOKEN"
	status_code = 400
	message = "リセットリンクが無効か、有効期限が切れています"


class ValidationError(AppError):
	code = "VALIDATION_ERROR"
	status_code = 422
	message = "入力内容に誤りがあります"


class ServiceUnavailableError(AppError):
	code = "SERVICE_UNAVAILABLE"
	status_code = 503
	message = "現在サービスをご利用いただけません"


def _build_error_body(code: str, message: str, details: Any, request_id: str) -> dict[str, Any]:
	return {
		"error": {
			"code": code,
			"message": message,
			"details": details,
			"request_id": request_id,
		}
	}


def _is_connection_operational_error(exc: OperationalError) -> bool:
	sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
	return isinstance(sqlstate, str) and (
		sqlstate.startswith(_POSTGRES_CONNECTION_SQLSTATE_PREFIX) or sqlstate in _POSTGRES_RETRYABLE_CONNECTION_STATES
	)


def is_service_unavailable_database_error(exc: Exception) -> bool:
	"""共通例外ハンドラが503へ変換するDB接続系例外か判定する。"""
	if isinstance(exc, InterfaceError):
		return True
	if isinstance(exc, OperationalError):
		return _is_connection_operational_error(exc)
	return isinstance(exc, (SQLAlchemyTimeoutError, DisconnectionError))


def raise_database_error(exc: DBAPIError) -> NoReturn:
	"""SQLSTATEに基づきDB障害だけを503へ変換し、それ以外は元の例外を伝播する。"""
	if isinstance(exc, OperationalError) and _is_connection_operational_error(exc):
		raise ServiceUnavailableError() from exc
	raise exc


def _infrastructure_error_response(exc: Exception) -> tuple[int, str, str]:
	if is_service_unavailable_database_error(exc):
		return 503, ServiceUnavailableError.code, ServiceUnavailableError.message
	if isinstance(exc, DBAPIError):
		return 500, "INTERNAL_ERROR", "サーバーエラーが発生しました"
	return 503, ServiceUnavailableError.code, ServiceUnavailableError.message


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
		if exc.status_code >= 500:
			event = (
				"service_unavailable" if exc.status_code == ServiceUnavailableError.status_code else "application_error"
			)
			logger.exception("application error", extra={"event": event, "request_id": request_id})
		headers = {}
		if isinstance(exc, TooManyAttemptsError) and exc.retry_after is not None:
			headers["Retry-After"] = str(exc.retry_after)
		return JSONResponse(
			status_code=exc.status_code,
			content=_build_error_body(exc.code, exc.message, exc.details, request_id),
			headers=headers,
		)

	@app.exception_handler(RedisError)
	async def infra_error_handler(request: Request, exc: Exception) -> JSONResponse:
		"""Redis/PostgreSQLの障害を設計上のステータスへ変換する。"""
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		status_code, error_code, message = _infrastructure_error_response(exc)
		event = "service_unavailable" if status_code == ServiceUnavailableError.status_code else "infrastructure_error"
		logger.exception("infrastructure error", extra={"event": event, "request_id": request_id})
		return JSONResponse(
			status_code=status_code,
			content=_build_error_body(error_code, message, None, request_id),
		)

	app.add_exception_handler(OperationalError, infra_error_handler)
	app.add_exception_handler(DBAPIError, infra_error_handler)
	app.add_exception_handler(InterfaceError, infra_error_handler)
	app.add_exception_handler(SQLAlchemyTimeoutError, infra_error_handler)
	app.add_exception_handler(DisconnectionError, infra_error_handler)

	@app.exception_handler(RequestValidationError)
	async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		details = [{"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]} for err in exc.errors()]
		return JSONResponse(
			status_code=422,
			content=_build_error_body("VALIDATION_ERROR", "入力内容に誤りがあります", details, request_id),
		)

	@app.exception_handler(PydanticValidationError)
	async def pydantic_validation_error_handler(request: Request, exc: PydanticValidationError) -> JSONResponse:
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		details = [{"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]} for err in exc.errors()]
		return JSONResponse(
			status_code=422,
			content=_build_error_body("VALIDATION_ERROR", "入力内容に誤りがあります", details, request_id),
		)

	@app.exception_handler(Exception)
	async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		logger.exception("unhandled exception", extra={"event": "unhandled_exception", "request_id": request_id})
		return JSONResponse(
			status_code=500,
			content=_build_error_body("INTERNAL_ERROR", "サーバーエラーが発生しました", None, request_id),
		)

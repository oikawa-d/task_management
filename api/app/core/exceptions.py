"""アプリ例外階層（`AppError`系）と、FastAPI例外ハンドラの一括登録を行うモジュール。

DB/Redis障害の503変換、バリデーションエラーの422整形、未捕捉例外の500整形など、
API共通のエラーレスポンス生成をここに集約する。
"""

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
	"""アプリ共通の例外基底クラス。code/status_code/messageをサブクラスで上書きし、
	register_error_handlingが一律のJSON形式へ変換する。"""

	code = "INTERNAL_ERROR"
	status_code = 500
	message = "サーバーエラーが発生しました"
	retry_after: int | None = None

	def __init__(self, message: str | None = None, details: Any = None) -> None:
		"""例外を初期化する。

		Args:
			message: クライアントへ返すエラーメッセージ。省略時はクラス属性`message`
				（デフォルトメッセージ）を使用する。
			details: エラーの詳細情報（バリデーション内容等）。レスポンスの`error.details`
				へそのまま含める。
		"""
		super().__init__(message or self.message)
		if message is not None:
			self.message = message
		self.details = details


class NotFoundError(AppError):
	"""対象リソースが存在しない場合の例外（HTTP 404）。"""

	code = "NOT_FOUND"
	status_code = 404
	message = "リソースが見つかりません"


class ForbiddenError(AppError):
	"""アクセス権が無い場合の例外（HTTP 403）。"""

	code = "FORBIDDEN"
	status_code = 403
	message = "このリソースへのアクセス権がありません"


class CsrfInvalidError(ForbiddenError):
	"""CSRFトークンの検証に失敗した場合の例外（HTTP 403）。"""

	code = "CSRF_INVALID"
	message = "CSRFトークンが不正です"


class ConflictError(AppError):
	"""リソースの競合が発生した場合の例外基底クラス（HTTP 409）。"""

	status_code = 409
	message = "競合が発生しました"


class TaskConflictError(ConflictError):
	"""楽観ロック等により、タスク更新が他ユーザーの更新と競合した場合の例外。"""

	code = "TASK_CONFLICT"
	message = "他のユーザーが先に更新しました。最新の内容を取得し直してください"


class AssigneeInactiveError(ConflictError):
	"""無効化されたユーザーをタスク担当者に指定しようとした場合の例外。"""

	code = "ASSIGNEE_INACTIVE"
	message = "無効なユーザーは担当者に指定できません"


class DuplicateUsernameError(ConflictError):
	"""既に使用されているユーザーIDで登録しようとした場合の例外。"""

	code = "DUPLICATE_USERNAME"
	message = "このユーザーIDは既に使用されています"


class DuplicateEmailError(ConflictError):
	"""既に使用されているメールアドレスで登録しようとした場合の例外。"""

	code = "DUPLICATE_EMAIL"
	message = "このメールアドレスは既に使用されています"


class AlreadyMemberError(ConflictError):
	"""既にプロジェクトメンバーであるユーザーを重複して招待しようとした場合の例外。"""

	code = "ALREADY_MEMBER"
	message = "既にプロジェクトのメンバーです"


class OwnerCannotBeRemovedError(ConflictError):
	"""プロジェクトオーナーをメンバーから削除しようとした場合の例外。"""

	code = "OWNER_CANNOT_BE_REMOVED"
	message = "オーナーはメンバーから削除できません"


class SelfModificationError(ConflictError):
	"""自分自身に対して許可されていない操作を行おうとした場合の例外。"""

	code = "SELF_MODIFICATION_NOT_ALLOWED"
	message = "自分自身に対してこの操作は実行できません"


class LastAdminRequiredError(ConflictError):
	"""最後の管理者に対して権限剥奪・無効化等を行おうとした場合の例外。"""

	code = "LAST_ADMIN_REQUIRED"
	message = "最後の管理者に対してこの操作は実行できません"


class UnauthenticatedError(AppError):
	"""未認証の場合の例外（HTTP 401）。"""

	code = "UNAUTHENTICATED"
	status_code = 401
	message = "認証が必要です"


class NotSupportedInModeError(AppError):
	"""現在の認証方式（session/jwt）ではサポートされない操作を要求された場合の例外（HTTP 405）。"""

	code = "NOT_SUPPORTED_IN_MODE"
	status_code = 405
	message = "現在の認証方式ではサポートされていません"


class SessionExpiredError(UnauthenticatedError):
	"""セッションの有効期限が切れている場合の例外。"""

	code = "SESSION_EXPIRED"
	message = "セッションの有効期限が切れました"


class TokenInvalidError(UnauthenticatedError):
	"""認証トークンの形式・署名が不正な場合の例外。"""

	code = "TOKEN_INVALID"
	message = "トークンが正しくありません"


class TokenExpiredError(UnauthenticatedError):
	"""認証トークンの有効期限が切れている場合の例外。"""

	code = "TOKEN_EXPIRED"
	message = "トークンの有効期限が切れています"


class TokenRevokedError(UnauthenticatedError):
	"""認証トークン（セッション）が失効済みの場合の例外。"""

	code = "TOKEN_REVOKED"
	message = "セッションが無効になりました。再度ログインしてください"


class InvalidStateError(AppError):
	"""OAuthのstateパラメータが無効な場合の例外（HTTP 400）。"""

	code = "INVALID_STATE"
	status_code = 400
	message = "OAuth stateが無効です"


class OAuthFailedError(AppError):
	"""OAuth認証フローが失敗した場合の例外（HTTP 400）。"""

	code = "OAUTH_FAILED"
	status_code = 400
	message = "OAuth認証に失敗しました"


class OAuthDisabledError(NotFoundError):
	"""Googleログイン機能が無効化されている場合の例外。"""

	code = "OAUTH_DISABLED"
	message = "Googleログインは現在無効です"


class OAuthEmailUnverifiedError(AppError):
	"""Googleアカウントのメールアドレスが未検証の場合の例外。"""

	code = "OAUTH_EMAIL_UNVERIFIED"
	status_code = 400
	message = "Googleアカウントのメールアドレスが検証されていません"


class OAuthHandoffInvalidError(AppError):
	"""OAuthログインの引き渡し（handoff）トークンが無効・期限切れの場合の例外。"""

	code = "OAUTH_HANDOFF_INVALID"
	status_code = 400
	message = "OAuthログインの有効期限が切れています"


class UserInactiveError(AppError):
	"""アカウントが無効化されているユーザーによる操作を拒否する例外（HTTP 403）。"""

	code = "USER_INACTIVE"
	status_code = 403
	message = "このアカウントは無効化されています"


class EmailNotVerifiedError(AppError):
	"""メールアドレスの検証が完了していないユーザーによる操作を拒否する例外。"""

	code = "EMAIL_NOT_VERIFIED"
	status_code = 403
	message = "メールアドレスの認証が完了していません"


class InvalidCredentialsError(UnauthenticatedError):
	"""ログインIDまたはパスワードが誤っている場合の例外。"""

	code = "INVALID_CREDENTIALS"
	message = "IDまたはパスワードが正しくありません"


class TooManyAttemptsError(AppError):
	"""レート制限・試行回数制限に達した場合の例外（HTTP 429）。`retry_after`秒後の再試行を示す。"""

	code = "TOO_MANY_ATTEMPTS"
	status_code = 429
	message = "試行回数が多いため、しばらく待ってから再度お試しください"

	def __init__(self, message: str | None = None, details: Any = None, retry_after: int | None = None) -> None:
		"""例外を初期化する。

		Args:
			message: クライアントへ返すエラーメッセージ。省略時はデフォルトメッセージを使用する。
			details: エラーの詳細情報。
			retry_after: クライアントに再試行を待たせる秒数。`app_error_handler`が
				`Retry-After`レスポンスヘッダへ設定する。
		"""
		super().__init__(message, details)
		self.retry_after = retry_after


class InvalidVerifyTokenError(AppError):
	"""メール認証リンクのトークンが無効・期限切れの場合の例外。"""

	code = "INVALID_VERIFY_TOKEN"
	status_code = 400
	message = "認証リンクが無効か、有効期限が切れています"


class InvalidResetTokenError(AppError):
	"""パスワードリセットリンクのトークンが無効・期限切れの場合の例外。"""

	code = "INVALID_RESET_TOKEN"
	status_code = 400
	message = "リセットリンクが無効か、有効期限が切れています"


class ValidationError(AppError):
	"""入力内容がドメインルールに違反する場合の例外（HTTP 422）。"""

	code = "VALIDATION_ERROR"
	status_code = 422
	message = "入力内容に誤りがあります"


class ServiceUnavailableError(AppError):
	"""DB/Redis等インフラ障害によりサービスを提供できない場合の例外（HTTP 503）。"""

	code = "SERVICE_UNAVAILABLE"
	status_code = 503
	message = "現在サービスをご利用いただけません"


def _build_error_body(code: str, message: str, details: Any, request_id: str) -> dict[str, Any]:
	"""API共通のエラーレスポンス形状（`{"error": {...}}`）を組み立てる。

	Args:
		code: エラーコード（例: `"NOT_FOUND"`）。クライアント側の分岐に使う安定識別子。
		message: 利用者向けの日本語エラーメッセージ。
		details: バリデーションエラー等の詳細情報。無ければNone。
		request_id: リクエストを一意に識別するID（ログとの突き合わせに使う）。

	Returns:
		`error`キー配下にcode/message/details/request_idをまとめた辞書。
	"""
	return {
		"error": {
			"code": code,
			"message": message,
			"details": details,
			"request_id": request_id,
		}
	}


def _is_connection_operational_error(exc: OperationalError) -> bool:
	"""PostgreSQLのSQLSTATEから、接続断・再接続可能な障害による`OperationalError`かを判定する。

	SQLSTATEクラス`08`（接続例外）、または個別に再試行可能と定義したコード
	（`_POSTGRES_RETRYABLE_CONNECTION_STATES`、例: `57P03` = クールダウン中）を対象とする。
	アプリのバグに起因するその他の`OperationalError`（構文エラー等）は対象外とし、
	誤って503へ丸めないようにする。

	Args:
		exc: 判定対象のSQLAlchemy `OperationalError`。

	Returns:
		接続断系の障害と判定できればTrue。
	"""
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
	"""Redis/DBインフラ例外を、`infra_error_handler`が返すべきステータス・コード・メッセージへ変換する。

	接続断系のDB障害と判定できる場合は503（サービス利用不可）とし、それ以外の
	`DBAPIError`（アプリのバグ等に起因しうるもの）は500として隠蔽する。
	それ以外（主にRedisの例外）は503として扱う。

	Args:
		exc: `app.exception_handler(RedisError)`経由で捕捉された例外
			（DB系の`add_exception_handler`登録分も含む）。

	Returns:
		`(status_code, error_code, message)`のタプル。
	"""
	if is_service_unavailable_database_error(exc):
		return 503, ServiceUnavailableError.code, ServiceUnavailableError.message
	if isinstance(exc, DBAPIError):
		return 500, "INTERNAL_ERROR", "サーバーエラーが発生しました"
	return 503, ServiceUnavailableError.code, ServiceUnavailableError.message


def register_error_handling(app: FastAPI) -> None:
	"""共通エラーハンドリング一式をFastAPIアプリへ登録する。

	以下を登録する。

	- `request_id_middleware`: 全リクエストにリクエストIDを付与し、レスポンスヘッダ
		（`X-Request-ID`）へ反映する。他のエラーハンドラがこのIDをログ・レスポンスへ
		含めるため、他のハンドラより先に（ミドルウェアとして最初に）動作する必要がある。
	- `app_error_handler`: `AppError`系（アプリ定義の例外）を、そのcode/status_codeに
		基づくJSONレスポンスへ変換する。
	- `infra_error_handler`: Redis例外、およびSQLAlchemyのDB接続系例外
		（`OperationalError`/`DBAPIError`/`InterfaceError`/`SQLAlchemyTimeoutError`/
		`DisconnectionError`）を、503（またはDBAPIErrorのバグ由来は500）へ変換する。
	- `validation_error_handler`/`pydantic_validation_error_handler`: リクエスト/
		スキーマのバリデーションエラーを422へ変換する。
	- `unhandled_exception_handler`: 上記のいずれにも該当しない未捕捉例外を500へ
		変換する（最後のフォールバック）。

	Args:
		app: ハンドラ・ミドルウェアを登録する対象のFastAPIアプリケーション。
	"""

	@app.middleware("http")
	async def request_id_middleware(request: Request, call_next: Any) -> Any:
		"""リクエストへ一意なリクエストIDを割り当て、レスポンスヘッダ`X-Request-ID`へ反映する。

		Args:
			request: 処理対象のHTTPリクエスト。
			call_next: 後続のミドルウェア/ルートハンドラを呼び出す関数。

		Returns:
			`X-Request-ID`ヘッダを付与したレスポンス。
		"""
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		request.state.request_id = request_id
		response = await call_next(request)
		response.headers["X-Request-ID"] = request_id
		return response

	@app.exception_handler(AppError)
	async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
		"""`AppError`系の例外を、そのcode/status_code/messageに基づくJSONレスポンスへ変換する。

		5xx系はサーバー側の異常としてログへ記録する。`TooManyAttemptsError`で
		`retry_after`が指定されている場合は`Retry-After`ヘッダを付与する。

		Args:
			request: 例外が発生したHTTPリクエスト。
			exc: 捕捉された`AppError`（またはそのサブクラス）。

		Returns:
			`exc.status_code`を持つ、共通エラーボディ形式のJSONレスポンス。
		"""
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
		"""FastAPIのリクエストバリデーションエラーを422のJSONレスポンスへ変換する。

		各エラーをフィールドパス（`.`区切り）とメッセージの組へ整形し、`details`へ含める。

		Args:
			request: 例外が発生したHTTPリクエスト。
			exc: パス/クエリ/ボディのバリデーションに失敗した際の例外。

		Returns:
			ステータス422、`VALIDATION_ERROR`コードのJSONレスポンス。
		"""
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		details = [{"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]} for err in exc.errors()]
		return JSONResponse(
			status_code=422,
			content=_build_error_body("VALIDATION_ERROR", "入力内容に誤りがあります", details, request_id),
		)

	@app.exception_handler(PydanticValidationError)
	async def pydantic_validation_error_handler(request: Request, exc: PydanticValidationError) -> JSONResponse:
		"""ルートハンドラ内で送出されたpydanticの`ValidationError`を422のJSONレスポンスへ変換する。

		FastAPIのリクエストバリデーション（`RequestValidationError`）とは別に、
		サービス層等で明示的にpydanticモデルを検証した際の失敗を同じ形式で返す。

		Args:
			request: 例外が発生したHTTPリクエスト。
			exc: pydanticモデルの検証失敗による例外。

		Returns:
			ステータス422、`VALIDATION_ERROR`コードのJSONレスポンス。
		"""
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		details = [{"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]} for err in exc.errors()]
		return JSONResponse(
			status_code=422,
			content=_build_error_body("VALIDATION_ERROR", "入力内容に誤りがあります", details, request_id),
		)

	@app.exception_handler(Exception)
	async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
		"""他のどのハンドラにも該当しない未捕捉例外を、内部情報を隠したまま500へ変換する最終フォールバック。

		詳細はクライアントへ返さず、スタックトレースをログへ記録することで
		調査可能性を確保する。

		Args:
			request: 例外が発生したHTTPリクエスト。
			exc: 想定外の未捕捉例外。

		Returns:
			ステータス500、`INTERNAL_ERROR`コードのJSONレスポンス。
		"""
		request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
		logger.exception("unhandled exception", extra={"event": "unhandled_exception", "request_id": request_id})
		return JSONResponse(
			status_code=500,
			content=_build_error_body("INTERNAL_ERROR", "サーバーエラーが発生しました", None, request_id),
		)

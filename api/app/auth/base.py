"""認証方式（session/jwt）を切り替えるStrategyパターンの共通インターフェースと型定義。

`AuthStrategy`のサブクラスがCookie発行・トークン検証・ログアウト・再発行といった
認証方式固有の実装（jwt_auth.py/session_auth.py）を提供する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Request, Response

from app.core.config import AuthMode, BackendSettings
from app.models.user import User


@dataclass(frozen=True)
class AuthContext:
	"""リクエストの認証結果として`authenticate`が返す最小限のユーザー識別情報。

	Args:
		user_id: 認証されたユーザーのID。
		role: 呼び出し元がロールを保持している場合のロール名（未設定ならDBから別途解決される）。
		username: 呼び出し元がユーザー名を保持している場合の値。
		session_id: sessionモードでのみ設定される、対象セッションのID。
	"""

	user_id: UUID
	role: str | None = None
	username: str | None = None
	session_id: str | None = None


@dataclass(frozen=True)
class LoginResult:
	"""ログイン・リフレッシュ処理の結果として発行された認証情報。

	Args:
		auth_mode: 発行元の認証方式（`session`または`jwt`）。
		access_token: jwtモードでのみ発行されるaccess token（JSONで返却される）。
		refresh_token: jwtモードでのみ発行されるrefresh token（Cookieに設定済み、値は内部処理用）。
		csrf_token: 更新系リクエストの検証に用いるCSRFトークン（Cookieに設定済み）。
		expires_in: access token（jwtモード）またはセッション（sessionモード）の有効期限（秒）。
		session_id: sessionモードでのみ発行されるセッションID。
		user_id: rollback時に失効対象を特定するためのユーザーID（等価比較・repr対象外）。
	"""

	auth_mode: AuthMode
	access_token: str | None = None
	refresh_token: str | None = None
	csrf_token: str | None = None
	expires_in: int | None = None
	session_id: str | None = None
	user_id: UUID | None = field(default=None, compare=False, repr=False)


class AuthStrategy(ABC):
	"""session/jwtの各認証方式が実装すべき共通インターフェース。"""

	mode: AuthMode

	def __init__(self, settings: BackendSettings) -> None:
		"""認証方式ごとのCookie名・TTL等を含む設定を保持して初期化する。

		Args:
			settings: Cookie属性・トークン有効期限等を含むバックエンド設定。
		"""
		self.settings = settings

	@abstractmethod
	async def login(self, user: User, request: Request, response: Response) -> LoginResult:
		"""認証成功後の認証状態（セッションまたはトークン）を発行し、`response`にCookieを設定する。

		Args:
			user: 認証済みユーザー。
			request: クライアントIP解決等に用いるリクエスト。
			response: Set-Cookie設定先のレスポンス。

		Returns:
			発行した認証情報。
		"""
		...

	@abstractmethod
	async def authenticate(self, request: Request) -> AuthContext | None:
		"""リクエストのCookieまたはAuthorizationヘッダから認証状態を検証する。

		Args:
			request: 検証対象のリクエスト。

		Returns:
			認証できた場合は`AuthContext`、Cookie/ヘッダが無く未認証と扱ってよい場合は`None`。

		Raises:
			SessionExpiredError: sessionモードでセッションが期限切れ・存在しない場合。
		"""
		...

	@abstractmethod
	async def logout(self, request: Request, response: Response) -> None:
		"""発行済みの認証状態（セッションまたはrefresh token）を失効させ、Cookieを削除する。

		Args:
			request: Cookie読み取りに用いるリクエスト。
			response: Cookie削除を反映するレスポンス。
		"""
		...

	@abstractmethod
	async def refresh(self, request: Request, response: Response) -> LoginResult:
		"""refresh tokenを検証・ローテーションし、新しい認証情報を発行する（jwtモード専用）。

		Args:
			request: refresh token Cookie読み取りに用いるリクエスト。
			response: 新しいCookie設定先のレスポンス。

		Returns:
			再発行した認証情報。

		Raises:
			NotSupportedInModeError: sessionモードでは再発行の概念が無いため送出する。
			TokenInvalidError: refresh token Cookieが存在しない場合。
			TokenRevokedError: refresh tokenが既に失効・再利用検知済みの場合。
		"""
		...

	async def rollback_login(self, user: User, result: LoginResult, response: Response) -> None:
		"""login後の後続処理に失敗した場合、発行済み認証状態を破棄する。"""
		raise NotImplementedError("rollback_login must be implemented by the auth strategy")

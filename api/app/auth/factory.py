"""設定値`auth_mode`に応じたAuthStrategy実装を選択するファクトリ。"""

from functools import lru_cache

from app.auth.base import AuthStrategy
from app.auth.jwt_auth import JwtAuthStrategy
from app.auth.session_auth import SessionAuthStrategy
from app.core.config import get_backend_settings


@lru_cache(maxsize=1)
def get_auth_strategy() -> AuthStrategy:
	"""現在の`auth_mode`設定に対応するAuthStrategyのシングルトンインスタンスを返す。

	プロセス内で使い回すため`lru_cache`でキャッシュする。FastAPIの依存性注入から
	`Depends(get_auth_strategy)`として利用される。

	Returns:
		`auth_mode`が`session`ならSessionAuthStrategy、`jwt`ならJwtAuthStrategyのインスタンス。

	Raises:
		ValueError: `auth_mode`が`session`・`jwt`のいずれでもない不正な設定値の場合。
	"""
	settings = get_backend_settings()
	if settings.auth_mode == "session":
		return SessionAuthStrategy(settings)
	if settings.auth_mode == "jwt":
		return JwtAuthStrategy(settings)
	raise ValueError(f"unsupported auth mode: {settings.auth_mode}")

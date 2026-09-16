"""認証方式のStrategy実装。"""

from app.auth.base import AuthContext, AuthStrategy, LoginResult
from app.auth.factory import get_auth_strategy

__all__ = ["AuthContext", "AuthStrategy", "LoginResult", "get_auth_strategy"]

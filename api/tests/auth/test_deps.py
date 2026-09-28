"""app.core.deps の get_current_user 系依存関数・レート制限(enforce_rate_limit系)・
ログアウト時CSRF検証(verify_csrf_for_logout)に対する単体テスト。
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.auth.base import AuthContext
from app.core.config import get_backend_settings
from app.core.deps import (
	enforce_notification_read_rate_limit,
	enforce_notification_write_rate_limit,
	enforce_rate_limit,
	get_current_user,
	get_current_user_optional,
	require_admin,
	verify_csrf_for_logout,
)
from app.core.exceptions import (
	ForbiddenError,
	ServiceUnavailableError,
	SessionExpiredError,
	TooManyAttemptsError,
	UnauthenticatedError,
	UserInactiveError,
)
from app.schemas.auth import CurrentUser


class _Strategy:
	"""指定した認証コンテキスト（またはNone）を固定で返すダミーAuthStrategy。"""

	def __init__(self, context: AuthContext | None):
		"""返却する認証コンテキストを保持する。

		Args:
			context: authenticate呼び出し時に返すAuthContext。Noneの場合は未認証を表す。
		"""
		self.context = context

	async def authenticate(self, request):
		"""保持しているcontextをそのまま返す（リクエスト内容は使わない）。"""
		return self.context


class _SessionExpiredStrategy:
	"""authenticate呼び出し時に必ずSessionExpiredErrorを送出するダミーAuthStrategy。"""

	async def authenticate(self, request):
		"""常にSessionExpiredErrorを送出し、セッション期限切れの状況を模擬する。"""
		raise SessionExpiredError()


def _user(user_id, *, active=True, role="member"):
	"""user_repository.get_by_idの戻り値を模擬するダミーユーザーレコードを作る。

	Args:
		user_id: ユーザーID。
		active: is_activeに設定する値。
		role: roleに設定する値。

	Returns:
		id・username・role・is_active・email_verified_atを持つSimpleNamespace。
	"""
	return SimpleNamespace(
		id=user_id,
		username="taro",
		role=role,
		is_active=active,
		email_verified_at=datetime.now(UTC),
	)


class _Db:
	"""get_current_user等へ渡すDBセッションの型を満たすだけのプレースホルダー（実際には使用されない）。"""


@pytest.mark.asyncio
async def test_get_current_user_uses_database_values(monkeypatch: pytest.MonkeyPatch) -> None:
	"""認証コンテキストの username/role が古い値でも、get_current_userはDBから取得した
	最新のユーザーレコード（user_repository.get_by_id）の値でCurrentUserを構築することを検証する。
	"""
	user_id = uuid4()
	monkeypatch.setattr(
		"app.core.deps.user_repository.get_by_id", AsyncMock(side_effect=lambda db, value: _user(value, role="admin"))
	)

	result = await get_current_user(None, _Strategy(AuthContext(user_id, role="member", username="old")), _Db())
	assert result == CurrentUser(
		id=user_id,
		username="taro",
		role="admin",
		is_active=True,
		email_verified_at=result.email_verified_at,
	)


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_and_inactive_users(monkeypatch: pytest.MonkeyPatch) -> None:
	"""認証コンテキストのuser_idに対応するユーザーがDBに存在しない場合はUnauthenticatedErrorを、
	存在するがis_active=Falseの場合はUserInactiveErrorを送出することを検証する。
	"""
	user_id = uuid4()
	monkeypatch.setattr("app.core.deps.user_repository.get_by_id", AsyncMock(return_value=None))
	with pytest.raises(UnauthenticatedError):
		await get_current_user(None, _Strategy(AuthContext(user_id)), _Db())

	monkeypatch.setattr(
		"app.core.deps.user_repository.get_by_id", AsyncMock(side_effect=lambda db, value: _user(value, active=False))
	)
	with pytest.raises(UserInactiveError):
		await get_current_user(None, _Strategy(AuthContext(user_id)), _Db())


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_context_and_require_admin_rejects_member() -> None:
	"""認証コンテキストがNone（未認証）の場合get_current_userはUnauthenticatedErrorを送出すること、
	またmemberロールのユーザーでrequire_adminを呼ぶとForbiddenErrorを送出することを検証する。
	"""
	with pytest.raises(UnauthenticatedError):
		await get_current_user(None, _Strategy(None), _Db())

	with pytest.raises(ForbiddenError):
		require_admin(CurrentUser(id=uuid4(), username="taro", role="member", is_active=True, email_verified_at=None))


@pytest.mark.asyncio
async def test_get_current_user_propagates_session_expired() -> None:
	"""AuthStrategy.authenticateがSessionExpiredErrorを送出した場合、get_current_userはそれを
	握りつぶさずそのまま伝播させることを検証する。
	"""
	with pytest.raises(SessionExpiredError):
		await get_current_user(None, _SessionExpiredStrategy(), _Db())


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_for_unauthenticated_request() -> None:
	"""未認証（認証コンテキストNone）のリクエストに対して、get_current_user_optionalは
	例外を送出せずNoneを返すことを検証する。
	"""
	assert await get_current_user_optional(None, _Strategy(None), _Db()) is None


class _CsrfRequest:
	"""verify_csrf_for_logout・enforce_rate_limit系が参照するCookie/ヘッダー/clientのみを持つダミーリクエスト。"""

	def __init__(self, cookies: dict[str, str], *, peer: str = "127.0.0.1", forwarded_for: str | None = None) -> None:
		"""Cookie・送信元IP・X-Forwarded-Forを指定してダミーリクエストを組み立てる。

		Args:
			cookies: リクエストに持たせるCookieの辞書。
			peer: client.hostとして参照される直接の送信元IP。
			forwarded_for: X-Forwarded-Forヘッダーの値。Noneの場合はヘッダー自体を持たせない。
		"""
		self.cookies = cookies
		self.headers: dict[str, str] = {"x-forwarded-for": forwarded_for} if forwarded_for else {}
		self.client = SimpleNamespace(host=peer)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["session", "jwt"])
async def test_verify_csrf_for_logout_skips_without_auth_cookie(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
	"""session/jwtいずれのモードでも、ログアウト対象の認証Cookie（セッションID/リフレッシュトークン）が
	無いリクエストではverify_csrf本体を呼び出さず、CSRF検証自体をスキップすることを検証する。
	"""
	verify_mock = AsyncMock()
	monkeypatch.setattr("app.core.deps.verify_csrf", verify_mock)
	settings = get_backend_settings()

	await verify_csrf_for_logout(_CsrfRequest({}), SimpleNamespace(mode=mode), settings)

	verify_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("mode", "cookie_name"),
	[("session", "cookie_name_session"), ("jwt", "cookie_name_refresh")],
)
async def test_verify_csrf_for_logout_validates_with_auth_cookie(
	monkeypatch: pytest.MonkeyPatch, mode: str, cookie_name: str
) -> None:
	"""ログアウト対象の認証Cookie（sessionモードはセッションID、jwtモードはリフレッシュトークン）が
	存在するリクエストでは、verify_csrf本体を1回呼び出してCSRF検証を実施することを検証する。
	"""
	verify_mock = AsyncMock()
	monkeypatch.setattr("app.core.deps.verify_csrf", verify_mock)
	settings = get_backend_settings()
	request = _CsrfRequest({getattr(settings, cookie_name): "value"})

	await verify_csrf_for_logout(request, SimpleNamespace(mode=mode), settings)

	verify_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_enforce_rate_limit_allows_request_within_limit(monkeypatch: pytest.MonkeyPatch) -> None:
	"""リクエスト回数が上限内の場合、enforce_rate_limitが生成する依存関数は例外を送出せず、
	redis_store.check_rate_limitへ操作名・クライアントIP・上限回数・ウィンドウ秒数を渡して
	呼び出すことを検証する。
	"""
	check_mock = AsyncMock(return_value=1)
	monkeypatch.setattr("app.core.deps.redis_store.check_rate_limit", check_mock)
	settings = get_backend_settings()
	dependency = enforce_rate_limit(
		"register", "rate_limit_register_max_requests", "rate_limit_register_window_seconds"
	)

	await dependency(_CsrfRequest({}), settings)

	assert check_mock.await_args.args == (
		"register",
		"127.0.0.1",
		settings.rate_limit_register_max_requests,
		settings.rate_limit_register_window_seconds,
	)


@pytest.mark.asyncio
async def test_enforce_rate_limit_rejects_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
	"""リクエスト回数が上限を超えた場合、TooManyAttemptsErrorを送出しretry_afterに
	redis_store.get_rate_limit_ttlで取得したTTL秒数が設定されることを検証する。
	"""
	settings = get_backend_settings()
	get_ttl = AsyncMock(return_value=742)
	monkeypatch.setattr(
		"app.core.deps.redis_store.check_rate_limit",
		AsyncMock(return_value=settings.rate_limit_register_max_requests + 1),
	)
	monkeypatch.setattr("app.core.deps.redis_store.get_rate_limit_ttl", get_ttl)
	dependency = enforce_rate_limit(
		"register", "rate_limit_register_max_requests", "rate_limit_register_window_seconds"
	)

	with pytest.raises(TooManyAttemptsError) as exc_info:
		await dependency(_CsrfRequest({}), settings)

	assert exc_info.value.retry_after == 742
	get_ttl.assert_awaited_once_with("register", "127.0.0.1")


@pytest.mark.asyncio
async def test_enforce_rate_limit_fails_closed_when_ttl_lookup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
	"""上限超過後のretry_after算出に必要なredis_store.get_rate_limit_ttlが例外を送出する場合、
	（TooManyAttemptsErrorではなく）ServiceUnavailableErrorを送出しfail-closeすることを検証する。
	"""
	settings = get_backend_settings()
	monkeypatch.setattr(
		"app.core.deps.redis_store.check_rate_limit",
		AsyncMock(return_value=settings.rate_limit_register_max_requests + 1),
	)
	monkeypatch.setattr(
		"app.core.deps.redis_store.get_rate_limit_ttl",
		AsyncMock(side_effect=RuntimeError("redis down")),
	)
	dependency = enforce_rate_limit(
		"register", "rate_limit_register_max_requests", "rate_limit_register_window_seconds"
	)

	with pytest.raises(ServiceUnavailableError):
		await dependency(_CsrfRequest({}), settings)


@pytest.mark.asyncio
async def test_enforce_rate_limit_fails_closed_on_redis_error(monkeypatch: pytest.MonkeyPatch) -> None:
	"""レート制限のカウント取得自体（redis_store.check_rate_limit）が例外を送出する場合、
	ServiceUnavailableErrorを送出しfail-closeすることを検証する。
	"""
	monkeypatch.setattr("app.core.deps.redis_store.check_rate_limit", AsyncMock(side_effect=RuntimeError("redis down")))
	dependency = enforce_rate_limit(
		"register", "rate_limit_register_max_requests", "rate_limit_register_window_seconds"
	)

	with pytest.raises(ServiceUnavailableError):
		await dependency(_CsrfRequest({}), get_backend_settings())


@pytest.mark.asyncio
async def test_notification_rate_limit_uses_resolved_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
	"""信頼済みプロキシ経由のリクエストでは、enforce_notification_read_rate_limitが
	X-Forwarded-Forから解決したクライアントIPを使い、"ユーザーID:クライアントIP"の形式の
	レート制限キーでredis_store.check_rate_limitを呼び出すことを検証する。
	"""
	user = CurrentUser(id=uuid4(), username="taro", role="member", is_active=True, email_verified_at=None)
	settings = get_backend_settings().model_copy(update={"trusted_proxy_cidrs": ["10.0.0.0/8"]})
	check_mock = AsyncMock(return_value=1)
	monkeypatch.setattr("app.core.deps.redis_store.check_rate_limit", check_mock)
	request = _CsrfRequest({}, peer="10.0.0.10", forwarded_for="198.51.100.20, 10.0.0.10")

	await enforce_notification_read_rate_limit(request, user, settings)

	assert check_mock.await_args.args[0] == "notification_read"
	assert check_mock.await_args.args[1] == f"{user.id}:198.51.100.20"


@pytest.mark.asyncio
async def test_notification_write_rate_limit_ignores_forwarded_ip_from_untrusted_peer(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""接続元IPが信頼済みプロキシCIDRに含まれない場合、enforce_notification_write_rate_limitは
	X-Forwarded-Forを無視し、直接の接続元IPを使ったレート制限キーでredis_store.check_rate_limitを
	呼び出すことを検証する。
	"""
	user = CurrentUser(id=uuid4(), username="taro", role="member", is_active=True, email_verified_at=None)
	settings = get_backend_settings().model_copy(update={"trusted_proxy_cidrs": ["10.0.0.0/8"]})
	check_mock = AsyncMock(return_value=1)
	monkeypatch.setattr("app.core.deps.redis_store.check_rate_limit", check_mock)
	request = _CsrfRequest({}, peer="192.0.2.10", forwarded_for="198.51.100.20, 10.0.0.10")

	await enforce_notification_write_rate_limit(request, user, settings)

	assert check_mock.await_args.args[0] == "notification_write"
	assert check_mock.await_args.args[1] == f"{user.id}:192.0.2.10"

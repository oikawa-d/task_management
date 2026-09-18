"""OAuthアカウント(oauth_accounts テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層が
同一セッションのcommitを担う。
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_account import OAuthAccount


async def get_by_provider_identity(db: AsyncSession, provider: str, provider_user_id: str) -> OAuthAccount | None:
	"""プロバイダ種別とプロバイダ側ユーザーIDに紐づくOAuthアカウントを1件取得する。

	DB関数 `fn_find_oauth_account` を呼び出し、oauth_accounts テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		provider: OAuthプロバイダ種別(例: "google")。
		provider_user_id: プロバイダ側のユーザー識別子。

	Returns:
		該当するOAuthAccount。該当行が存在しない場合はNone。
	"""
	result = await db.execute(
		select(OAuthAccount)
		.from_statement(text("SELECT * FROM fn_find_oauth_account(:provider, :provider_user_id)"))
		.params(provider=provider, provider_user_id=provider_user_id)
	)
	return result.scalars().one_or_none()


async def list_by_user_id(db: AsyncSession, user_id: uuid.UUID) -> list[OAuthAccount]:
	"""指定ユーザーに紐づくOAuthアカウントを全件取得する。

	DB関数 `fn_list_user_oauth_accounts` を呼び出し、oauth_accounts テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。

	Returns:
		該当するOAuthAccountのリスト。該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		select(OAuthAccount)
		.from_statement(text("SELECT * FROM fn_list_user_oauth_accounts(:user_id)"))
		.params(user_id=user_id)
	)
	return list(result.scalars().all())


async def upsert(db: AsyncSession, user_id: uuid.UUID, provider: str, provider_user_id: str) -> None:
	"""ユーザーとプロバイダの組み合わせでOAuthアカウントを新規作成または更新する。

	ストアドプロシージャ `sp_upsert_oauth_account` を呼び出し、oauth_accounts テーブルを
	更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		user_id: 紐づけるユーザーID。
		provider: OAuthプロバイダ種別。
		provider_user_id: プロバイダ側のユーザー識別子。

	Returns:
		None。
	"""
	await db.execute(
		text("CALL sp_upsert_oauth_account(:user_id, :provider, :provider_user_id)"),
		{"user_id": user_id, "provider": provider, "provider_user_id": provider_user_id},
	)

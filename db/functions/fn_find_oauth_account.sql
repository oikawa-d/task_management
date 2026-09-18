-- 概要: OAuthプロバイダ名とプロバイダ側ユーザーIDの組で連携済みOAuthアカウントを検索する
-- 引数: p_provider VARCHAR — OAuthプロバイダ名／p_provider_user_id TEXT — プロバイダ側のユーザー識別子
-- 戻り値: SETOF oauth_accounts — 合致するOAuthアカウント行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/oauth_account_repository.py
CREATE OR REPLACE FUNCTION fn_find_oauth_account(
    p_provider VARCHAR,
    p_provider_user_id TEXT
) RETURNS SETOF oauth_accounts
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM oauth_accounts
    WHERE provider = p_provider
      AND provider_user_id = p_provider_user_id;
$$;

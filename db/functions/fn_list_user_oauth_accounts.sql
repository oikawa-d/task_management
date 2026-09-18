-- 概要: 指定ユーザーが連携済みのOAuthアカウント一覧を取得する
-- 引数: p_user_id UUID — 対象ユーザーID
-- 戻り値: SETOF oauth_accounts — 連携済みOAuthアカウント行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/oauth_account_repository.py
CREATE OR REPLACE FUNCTION fn_list_user_oauth_accounts(
    p_user_id UUID
) RETURNS SETOF oauth_accounts
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM oauth_accounts WHERE user_id = p_user_id;
$$;

-- 概要: 指定ユーザーのログイン履歴を作成日時の降順・ページングで取得する
-- 引数: p_user_id UUID — 対象ユーザーID／p_limit INTEGER — 取得件数上限／p_offset INTEGER — 取得開始位置
-- 戻り値: SETOF login_history — 作成日時降順のログイン履歴行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/login_history_repository.py
CREATE OR REPLACE FUNCTION fn_list_user_login_history(
    p_user_id UUID,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF login_history
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM login_history
    WHERE user_id = p_user_id
    ORDER BY created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

-- 状態: 現役（根拠: alembic api/alembic/versions/0020_add_admin_list_total_count_and_not_found.py の
--       downgrade() から参照される。同名の現役オブジェクトが db/functions/fn_admin_list_login_history.sql に存在する）
-- 概要: 管理者向けログイン履歴一覧を取得する。総件数を返さない、件数返却導入前の版。
-- 引数: p_user_id UUID — 対象ユーザーIDによる絞り込み（NULLで全ユーザー対象）
--       p_query VARCHAR — ログイン識別子の部分一致検索語（NULLで絞り込みなし）
--       p_login_method VARCHAR — ログイン方式による絞り込み（NULLで全件）
--       p_success BOOLEAN — 成功/失敗による絞り込み（NULLで全件）
--       p_from TIMESTAMPTZ — 検索期間の開始（NULLで下限なし）
--       p_to TIMESTAMPTZ — 検索期間の終了（NULLで上限なし）
--       p_limit INTEGER — 取得件数上限
--       p_offset INTEGER — 取得開始位置
-- 戻り値: SETOF login_history — 条件に合致するログイン履歴レコード
-- 副作用: なし
CREATE OR REPLACE FUNCTION fn_admin_list_login_history(
    p_user_id UUID,
    p_query VARCHAR,
    p_login_method VARCHAR,
    p_success BOOLEAN,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF login_history
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM login_history
    WHERE (p_user_id IS NULL OR user_id = p_user_id)
      AND (p_query IS NULL OR lower(login_identifier) LIKE '%' || lower(p_query) || '%')
      AND (p_login_method IS NULL OR login_method = p_login_method)
      AND (p_success IS NULL OR success = p_success)
      AND (p_from IS NULL OR created_at >= p_from)
      AND (p_to IS NULL OR created_at < p_to)
    ORDER BY created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

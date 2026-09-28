-- 状態: 現役（根拠: alembic api/alembic/versions/0022_optimize_admin_list_functions.py の downgrade() と、
--       api/tests/repository/test_admin_repository.py がファイル存在を検証するテストの双方から参照される。
--       同名の現役オブジェクトが db/functions/fn_admin_list_login_history.sql に存在する）
-- 概要: 管理者向けログイン履歴一覧を、該当件数(total_count)付きで取得する。
--       ウィンドウ関数で絞り込み後の総件数を各行に付与する、最適化前の版。
-- 引数: p_user_id UUID — 対象ユーザーIDによる絞り込み（NULLで全ユーザー対象）
--       p_query VARCHAR — ログイン識別子の部分一致検索語（NULLで絞り込みなし）
--       p_login_method VARCHAR — ログイン方式による絞り込み（NULLで全件）
--       p_success BOOLEAN — 成功/失敗による絞り込み（NULLで全件）
--       p_from TIMESTAMPTZ — 検索期間の開始（NULLで下限なし）
--       p_to TIMESTAMPTZ — 検索期間の終了（NULLで上限なし）
--       p_limit INTEGER — 取得件数上限
--       p_offset INTEGER — 取得開始位置
-- 戻り値: TABLE(history login_history, total_count BIGINT) — 条件に合致するログイン履歴と、
--       ページングを適用する前の絞り込み後総件数
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
) RETURNS TABLE (
    history login_history,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT h.id, count(*) OVER () AS total_count
        FROM login_history h
        WHERE (p_user_id IS NULL OR h.user_id = p_user_id)
          AND (p_query IS NULL OR lower(h.login_identifier) LIKE '%' || lower(p_query) || '%')
          AND (p_login_method IS NULL OR h.login_method = p_login_method)
          AND (p_success IS NULL OR h.success = p_success)
          AND (p_from IS NULL OR h.created_at >= p_from)
          AND (p_to IS NULL OR h.created_at < p_to)
        ORDER BY h.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT h AS history, s.total_count
    FROM scoped s
    JOIN login_history h ON h.id = s.id
    ORDER BY h.created_at DESC;
$$;

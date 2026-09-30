-- 状態: 現役（根拠: alembic api/alembic/versions/0022_optimize_admin_list_functions.py の downgrade() と、
--       api/tests/repository/test_admin_repository.py がファイル存在を検証するテストの双方から参照される。
--       同名の現役オブジェクトが db/functions/fn_admin_list_projects.sql に存在する）
-- 概要: 管理者向けプロジェクト一覧を、該当件数(total_count)付きで取得する。
--       ウィンドウ関数で絞り込み後の総件数を各行に付与する、最適化前の版。
-- 引数: p_query VARCHAR — プロジェクト名の部分一致検索語（NULLで絞り込みなし）
--       p_is_active BOOLEAN — 有効/無効による絞り込み（NULLで全件）
--       p_limit INTEGER — 取得件数上限
--       p_offset INTEGER — 取得開始位置
-- 戻り値: TABLE(project projects, total_count BIGINT) — 条件に合致するプロジェクトと、
--       ページングを適用する前の絞り込み後総件数
-- 副作用: なし
CREATE OR REPLACE FUNCTION fn_admin_list_projects(
    p_query VARCHAR,
    p_is_active BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    project projects,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT p.id, count(*) OVER () AS total_count
        FROM projects p
        WHERE (p_query IS NULL OR lower(p.name) LIKE '%' || lower(p_query) || '%')
          AND (p_is_active IS NULL OR p.is_active = p_is_active)
        ORDER BY p.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT p AS project, s.total_count
    FROM scoped s
    JOIN projects p ON p.id = s.id
    ORDER BY p.created_at DESC;
$$;

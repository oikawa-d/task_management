-- 状態: 現役（根拠: alembic api/alembic/versions/0020_add_admin_list_total_count_and_not_found.py の
--       downgrade() から参照される。同名の現役オブジェクトが db/functions/fn_admin_list_projects.sql に存在する）
-- 概要: 管理者向けプロジェクト一覧を取得する。総件数を返さない、件数返却導入前の版。
-- 引数: p_query VARCHAR — プロジェクト名の部分一致検索語（NULLで絞り込みなし）
--       p_is_active BOOLEAN — 有効/無効による絞り込み（NULLで全件）
--       p_limit INTEGER — 取得件数上限
--       p_offset INTEGER — 取得開始位置
-- 戻り値: SETOF projects — 条件に合致するプロジェクトレコード
-- 副作用: なし
CREATE OR REPLACE FUNCTION fn_admin_list_projects(
    p_query VARCHAR,
    p_is_active BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF projects
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM projects
    WHERE (p_query IS NULL OR lower(name) LIKE '%' || lower(p_query) || '%')
      AND (p_is_active IS NULL OR is_active = p_is_active)
    ORDER BY created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

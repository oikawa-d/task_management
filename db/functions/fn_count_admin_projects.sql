-- 概要: 管理者向けプロジェクト一覧と同じ検索条件に合致する件数のみを算出する（ページング用の総件数取得）
-- 引数: p_query VARCHAR — プロジェクト名の部分一致検索語（NULLで無視）／p_is_active BOOLEAN — 有効/無効で絞り込み（NULLで無視）
-- 戻り値: BIGINT — 条件に合致するプロジェクトの件数
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/admin_repository.py
CREATE OR REPLACE FUNCTION fn_count_admin_projects(
    p_query VARCHAR,
    p_is_active BOOLEAN
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM projects p
    WHERE (p_query IS NULL OR lower(p.name) LIKE '%' || lower(p_query) || '%')
      AND (p_is_active IS NULL OR p.is_active = p_is_active);
$$;

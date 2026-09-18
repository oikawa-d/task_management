-- 概要: IDを指定してプロジェクト1件を取得する
-- 引数: p_project_id UUID — 取得対象のプロジェクトID
-- 戻り値: SETOF projects — 合致するプロジェクト行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/project_repository.py
CREATE OR REPLACE FUNCTION fn_get_project(
    p_project_id UUID
) RETURNS SETOF projects
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM projects WHERE id = p_project_id;
$$;

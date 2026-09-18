-- 概要: 指定プロジェクトのメンバー一覧を参加日時の昇順で取得する
-- 引数: p_project_id UUID — 対象プロジェクトID
-- 戻り値: SETOF project_members — 参加日時昇順のメンバー行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/project_member_repository.py
CREATE OR REPLACE FUNCTION fn_list_project_members(
    p_project_id UUID
) RETURNS SETOF project_members
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM project_members
    WHERE project_id = p_project_id
    ORDER BY joined_at ASC;
$$;

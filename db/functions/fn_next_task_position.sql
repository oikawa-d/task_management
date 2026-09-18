-- 概要: 指定プロジェクト（またはプロジェクト未所属）かつ指定ステータス内で、タスクを末尾に追加する際の次の並び順(position)を算出する
-- 引数: p_project_id UUID — 対象プロジェクトID（NULLでプロジェクト未所属タスクを対象）／p_status VARCHAR — 対象ステータス
-- 戻り値: INTEGER — 同一プロジェクト・ステータス内の最大positionに1を加えた値（該当タスクが無い場合は0）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: db/procedures/sp_create_task.sql, db/procedures/sp_update_task.sql
CREATE OR REPLACE FUNCTION fn_next_task_position(
    p_project_id UUID,
    p_status VARCHAR
) RETURNS INTEGER
LANGUAGE sql
AS $$
    -- project_id = p_project_id ではp_project_idがNULLの場合に常にNULL（非該当）となり
    -- 未所属タスク（project_id IS NULL）の採番が常に0を返す不具合になるため、
    -- IS NOT DISTINCT FROM でNULL同士も一致とみなす
    SELECT COALESCE(MAX(position), -1) + 1
    FROM tasks
    WHERE project_id IS NOT DISTINCT FROM p_project_id
      AND status = p_status;
$$;

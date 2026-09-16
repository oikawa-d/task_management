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

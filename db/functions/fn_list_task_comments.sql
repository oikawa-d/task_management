CREATE OR REPLACE FUNCTION fn_list_task_comments(
    p_task_id UUID
) RETURNS SETOF task_comments
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM task_comments
    WHERE task_id = p_task_id
    ORDER BY created_at ASC;
$$;

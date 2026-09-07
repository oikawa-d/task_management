CREATE OR REPLACE FUNCTION fn_get_task(
    p_task_id UUID
) RETURNS SETOF tasks
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM tasks WHERE id = p_task_id;
$$;

CREATE OR REPLACE FUNCTION fn_get_task(
    p_task_id UUID
) RETURNS TABLE (
    task tasks,
    project_is_active BOOLEAN
)
LANGUAGE sql
STABLE
AS $$
    SELECT t, p.is_active
    FROM tasks t
    LEFT JOIN projects p ON p.id = t.project_id
    WHERE t.id = p_task_id;
$$;

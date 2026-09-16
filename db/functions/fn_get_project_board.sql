CREATE OR REPLACE FUNCTION fn_get_project_board(
    p_project_id UUID,
    p_include_inactive BOOLEAN
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
    WHERE t.project_id = p_project_id
      AND (p_include_inactive OR t.is_active = true)
    ORDER BY t.status, t.position;
$$;

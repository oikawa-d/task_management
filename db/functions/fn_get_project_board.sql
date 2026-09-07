CREATE OR REPLACE FUNCTION fn_get_project_board(
    p_project_id UUID,
    p_include_inactive BOOLEAN
) RETURNS SETOF tasks
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM tasks
    WHERE project_id = p_project_id
      AND (p_include_inactive OR is_active = true)
    ORDER BY status, position;
$$;

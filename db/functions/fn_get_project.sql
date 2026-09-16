CREATE OR REPLACE FUNCTION fn_get_project(
    p_project_id UUID
) RETURNS SETOF projects
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM projects WHERE id = p_project_id;
$$;

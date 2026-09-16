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

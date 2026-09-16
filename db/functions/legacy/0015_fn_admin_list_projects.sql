CREATE OR REPLACE FUNCTION fn_admin_list_projects(
    p_query VARCHAR,
    p_is_active BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF projects
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM projects
    WHERE (p_query IS NULL OR lower(name) LIKE '%' || lower(p_query) || '%')
      AND (p_is_active IS NULL OR is_active = p_is_active)
    ORDER BY created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

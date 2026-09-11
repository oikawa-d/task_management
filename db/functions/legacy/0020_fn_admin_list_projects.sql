CREATE OR REPLACE FUNCTION fn_admin_list_projects(
    p_query VARCHAR,
    p_is_active BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    project projects,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT p.id, count(*) OVER () AS total_count
        FROM projects p
        WHERE (p_query IS NULL OR lower(p.name) LIKE '%' || lower(p_query) || '%')
          AND (p_is_active IS NULL OR p.is_active = p_is_active)
        ORDER BY p.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT p AS project, s.total_count
    FROM scoped s
    JOIN projects p ON p.id = s.id
    ORDER BY p.created_at DESC;
$$;

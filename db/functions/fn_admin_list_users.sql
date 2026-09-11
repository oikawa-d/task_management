CREATE OR REPLACE FUNCTION fn_admin_list_users(
    p_query VARCHAR,
    p_role VARCHAR,
    p_is_active BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    "user" users,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT u.id, count(*) OVER () AS total_count
        FROM users u
        WHERE (p_query IS NULL OR lower(u.username) LIKE '%' || lower(p_query) || '%'
                               OR lower(u.email) LIKE '%' || lower(p_query) || '%')
          AND (p_role IS NULL OR u.role = p_role)
          AND (p_is_active IS NULL OR u.is_active = p_is_active)
        ORDER BY u.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT u AS "user", s.total_count
    FROM scoped s
    JOIN users u ON u.id = s.id
    ORDER BY u.created_at DESC;
$$;

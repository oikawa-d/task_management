CREATE OR REPLACE FUNCTION fn_count_admin_users(
    p_query VARCHAR,
    p_role VARCHAR,
    p_is_active BOOLEAN
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM users u
    WHERE (p_query IS NULL OR lower(u.username) LIKE '%' || lower(p_query) || '%'
                           OR lower(u.email) LIKE '%' || lower(p_query) || '%')
      AND (p_role IS NULL OR u.role = p_role)
      AND (p_is_active IS NULL OR u.is_active = p_is_active);
$$;

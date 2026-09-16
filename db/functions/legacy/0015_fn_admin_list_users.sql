CREATE OR REPLACE FUNCTION fn_admin_list_users(
    p_query VARCHAR,
    p_role VARCHAR,
    p_is_active BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF users
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM users
    WHERE (p_query IS NULL OR lower(username) LIKE '%' || lower(p_query) || '%'
                           OR lower(email) LIKE '%' || lower(p_query) || '%')
      AND (p_role IS NULL OR role = p_role)
      AND (p_is_active IS NULL OR is_active = p_is_active)
    ORDER BY created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

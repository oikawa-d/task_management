CREATE OR REPLACE FUNCTION fn_admin_list_login_history(
    p_user_id UUID,
    p_query VARCHAR,
    p_login_method VARCHAR,
    p_success BOOLEAN,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    history login_history,
    "user" users,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT h.id, count(*) OVER () AS total_count
        FROM login_history h
        WHERE (p_user_id IS NULL OR h.user_id = p_user_id)
          AND (p_query IS NULL OR lower(h.login_identifier) LIKE '%' || lower(p_query) || '%')
          AND (p_login_method IS NULL OR h.login_method = p_login_method)
          AND (p_success IS NULL OR h.success = p_success)
          AND (p_from IS NULL OR h.created_at >= p_from)
          AND (p_to IS NULL OR h.created_at < p_to)
        ORDER BY h.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT h AS history, u AS "user", s.total_count
    FROM scoped s
    JOIN login_history h ON h.id = s.id
    LEFT JOIN users u ON u.id = h.user_id
    ORDER BY h.created_at DESC;
$$;

CREATE OR REPLACE FUNCTION fn_admin_list_login_history(
    p_user_id UUID,
    p_query VARCHAR,
    p_login_method VARCHAR,
    p_success BOOLEAN,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF login_history
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM login_history
    WHERE (p_user_id IS NULL OR user_id = p_user_id)
      AND (p_query IS NULL OR lower(login_identifier) LIKE '%' || lower(p_query) || '%')
      AND (p_login_method IS NULL OR login_method = p_login_method)
      AND (p_success IS NULL OR success = p_success)
      AND (p_from IS NULL OR created_at >= p_from)
      AND (p_to IS NULL OR created_at <= p_to)
    ORDER BY created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

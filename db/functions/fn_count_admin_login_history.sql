CREATE OR REPLACE FUNCTION fn_count_admin_login_history(
    p_user_id UUID,
    p_query VARCHAR,
    p_login_method VARCHAR,
    p_success BOOLEAN,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM login_history h
    WHERE (p_user_id IS NULL OR h.user_id = p_user_id)
      AND (p_query IS NULL OR lower(h.login_identifier) LIKE '%' || lower(p_query) || '%')
      AND (p_login_method IS NULL OR h.login_method = p_login_method)
      AND (p_success IS NULL OR h.success = p_success)
      AND (p_from IS NULL OR h.created_at >= p_from)
      AND (p_to IS NULL OR h.created_at < p_to);
$$;

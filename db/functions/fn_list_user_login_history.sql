CREATE OR REPLACE FUNCTION fn_list_user_login_history(
    p_user_id UUID,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF login_history
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM login_history
    WHERE user_id = p_user_id
    ORDER BY created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

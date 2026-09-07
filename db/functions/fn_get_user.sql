CREATE OR REPLACE FUNCTION fn_get_user(
    p_user_id UUID
) RETURNS SETOF users
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM users WHERE id = p_user_id;
$$;

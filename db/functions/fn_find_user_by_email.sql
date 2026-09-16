CREATE OR REPLACE FUNCTION fn_find_user_by_email(
    p_email VARCHAR
) RETURNS SETOF users
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM users WHERE lower(email) = lower(p_email);
$$;

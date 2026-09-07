CREATE OR REPLACE FUNCTION fn_find_user_by_identifier(
    p_identifier VARCHAR
) RETURNS SETOF users
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM users
    WHERE lower(username) = lower(p_identifier)
       OR lower(email) = lower(p_identifier);
$$;

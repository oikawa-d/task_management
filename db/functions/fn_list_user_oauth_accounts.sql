CREATE OR REPLACE FUNCTION fn_list_user_oauth_accounts(
    p_user_id UUID
) RETURNS SETOF oauth_accounts
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM oauth_accounts WHERE user_id = p_user_id;
$$;

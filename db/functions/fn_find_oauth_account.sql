CREATE OR REPLACE FUNCTION fn_find_oauth_account(
    p_provider VARCHAR,
    p_provider_user_id TEXT
) RETURNS SETOF oauth_accounts
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM oauth_accounts
    WHERE provider = p_provider
      AND provider_user_id = p_provider_user_id;
$$;

CREATE OR REPLACE PROCEDURE sp_upsert_oauth_account(
    p_user_id UUID,
    p_provider VARCHAR,
    p_provider_user_id TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO oauth_accounts (user_id, provider, provider_user_id)
    VALUES (p_user_id, p_provider, p_provider_user_id)
    ON CONFLICT (provider, provider_user_id) DO NOTHING;

    UPDATE users
       SET email_verified_at = COALESCE(email_verified_at, now())
     WHERE id = p_user_id;
END;
$$;

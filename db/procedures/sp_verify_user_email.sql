CREATE OR REPLACE PROCEDURE sp_verify_user_email(
    p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE users SET email_verified_at = now() WHERE id = p_user_id;
END;
$$;

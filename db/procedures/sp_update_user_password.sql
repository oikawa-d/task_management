CREATE OR REPLACE PROCEDURE sp_update_user_password(
    p_user_id UUID,
    p_password_hash TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE users SET password_hash = p_password_hash WHERE id = p_user_id;
END;
$$;

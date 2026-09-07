CREATE OR REPLACE PROCEDURE sp_register_user(
    p_username VARCHAR,
    p_email VARCHAR,
    p_password_hash TEXT,
    OUT p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE lower(username) = lower(p_username)) THEN
        RAISE EXCEPTION 'username already exists' USING ERRCODE = 'P0001';
    END IF;

    IF EXISTS (SELECT 1 FROM users WHERE lower(email) = lower(p_email)) THEN
        RAISE EXCEPTION 'email already exists' USING ERRCODE = 'P0002';
    END IF;

    INSERT INTO users (username, email, password_hash)
    VALUES (p_username, p_email, p_password_hash)
    RETURNING id INTO p_user_id;
END;
$$;

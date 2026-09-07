CREATE OR REPLACE PROCEDURE sp_update_user_profile(
    p_user_id UUID,
    p_last_name VARCHAR,
    p_first_name VARCHAR,
    p_last_name_kana VARCHAR,
    p_first_name_kana VARCHAR,
    p_birth_date DATE
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE users
       SET last_name = p_last_name,
           first_name = p_first_name,
           last_name_kana = p_last_name_kana,
           first_name_kana = p_first_name_kana,
           birth_date = p_birth_date
     WHERE id = p_user_id;
END;
$$;

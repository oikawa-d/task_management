CREATE OR REPLACE PROCEDURE sp_mark_all_notifications_read(
    p_user_id UUID,
    OUT p_updated_count INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE notifications
       SET read_at = now()
     WHERE user_id = p_user_id
       AND read_at IS NULL;

    GET DIAGNOSTICS p_updated_count = ROW_COUNT;
END;
$$;

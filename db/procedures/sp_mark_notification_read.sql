CREATE OR REPLACE PROCEDURE sp_mark_notification_read(
    p_notification_id UUID,
    p_user_id UUID,
    OUT p_read_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    SELECT read_at
      INTO p_read_at
      FROM notifications
     WHERE id = p_notification_id
       AND user_id = p_user_id
     FOR UPDATE;

    IF NOT FOUND THEN
        p_read_at := NULL;
        RETURN;
    END IF;

    UPDATE notifications
       SET read_at = COALESCE(read_at, now())
     WHERE id = p_notification_id
       AND user_id = p_user_id
     RETURNING read_at INTO p_read_at;
END;
$$;

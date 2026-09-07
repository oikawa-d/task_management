CREATE OR REPLACE FUNCTION fn_count_unread_notifications(
    p_user_id UUID
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM notifications
    WHERE user_id = p_user_id
      AND read_at IS NULL;
$$;

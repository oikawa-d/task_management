CREATE OR REPLACE FUNCTION fn_count_notifications(
    p_user_id UUID,
    p_unread_only BOOLEAN
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM notifications n
    WHERE n.user_id = p_user_id
      AND (p_unread_only = false OR n.read_at IS NULL);
$$;

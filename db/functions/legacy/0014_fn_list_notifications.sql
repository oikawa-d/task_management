CREATE OR REPLACE FUNCTION fn_list_notifications(
    p_user_id UUID,
    p_unread_only BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF notifications
LANGUAGE sql
STABLE
AS $$
    SELECT n.*
    FROM notifications n
    WHERE n.user_id = p_user_id
      AND (p_unread_only = false OR n.read_at IS NULL)
    ORDER BY n.created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

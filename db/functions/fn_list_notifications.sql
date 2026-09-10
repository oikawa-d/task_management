CREATE OR REPLACE FUNCTION fn_list_notifications(
    p_user_id UUID,
    p_unread_only BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    notification notifications,
    task_title VARCHAR,
    task_project_id UUID,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT n.id, count(*) OVER () AS total_count
        FROM notifications n
        WHERE n.user_id = p_user_id
          AND (p_unread_only = false OR n.read_at IS NULL)
        ORDER BY n.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT
        n AS notification,
        t.title AS task_title,
        t.project_id AS task_project_id,
        s.total_count
    FROM scoped s
    JOIN notifications n ON n.id = s.id
    LEFT JOIN tasks t ON t.id = n.task_id
    ORDER BY n.created_at DESC;
$$;

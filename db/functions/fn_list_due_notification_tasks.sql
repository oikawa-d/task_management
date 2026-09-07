CREATE OR REPLACE FUNCTION fn_list_due_notification_tasks(
    p_threshold TIMESTAMPTZ
) RETURNS SETOF tasks
LANGUAGE sql
STABLE
AS $$
    SELECT *
    FROM tasks
    WHERE due_at < p_threshold
      AND is_active = true
      AND assignee_id IS NOT NULL;
$$;

CREATE OR REPLACE FUNCTION fn_get_task(
    p_task_id UUID
) RETURNS TABLE (
    task tasks,
    project_is_active BOOLEAN,
    comment_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH comment_counts AS (
        SELECT task_id, count(*) AS comment_count
        FROM task_comments
        WHERE task_id = p_task_id
        GROUP BY task_id
    )
    SELECT t, p.is_active, COALESCE(cc.comment_count, 0)
    FROM tasks t
    LEFT JOIN projects p ON p.id = t.project_id
    LEFT JOIN comment_counts cc ON cc.task_id = t.id
    WHERE t.id = p_task_id;
$$;

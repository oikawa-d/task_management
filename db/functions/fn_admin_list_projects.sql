CREATE OR REPLACE FUNCTION fn_admin_list_projects(
    p_query VARCHAR,
    p_is_active BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    project projects,
    member_count BIGINT,
    task_count_todo BIGINT,
    task_count_in_progress BIGINT,
    task_count_done BIGINT,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT p.id, count(*) OVER () AS total_count
        FROM projects p
        WHERE (p_query IS NULL OR lower(p.name) LIKE '%' || lower(p_query) || '%')
          AND (p_is_active IS NULL OR p.is_active = p_is_active)
        ORDER BY p.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT
        p AS project,
        COALESCE(member_counts.member_count, 0) AS member_count,
        COALESCE(task_counts.task_count_todo, 0) AS task_count_todo,
        COALESCE(task_counts.task_count_in_progress, 0) AS task_count_in_progress,
        COALESCE(task_counts.task_count_done, 0) AS task_count_done,
        s.total_count
    FROM scoped s
    JOIN projects p ON p.id = s.id
    LEFT JOIN (
        SELECT project_id, count(*) AS member_count
        FROM project_members
        WHERE project_id IN (SELECT id FROM scoped)
        GROUP BY project_id
    ) AS member_counts ON member_counts.project_id = p.id
    LEFT JOIN (
        SELECT
            project_id,
            count(*) FILTER (WHERE status = 'todo') AS task_count_todo,
            count(*) FILTER (WHERE status = 'in_progress') AS task_count_in_progress,
            count(*) FILTER (WHERE status = 'done') AS task_count_done
        FROM tasks
        WHERE project_id IN (SELECT id FROM scoped)
        GROUP BY project_id
    ) AS task_counts ON task_counts.project_id = p.id
    ORDER BY p.created_at DESC;
$$;

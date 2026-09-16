CREATE OR REPLACE FUNCTION fn_list_projects(
    p_user_id UUID,
    p_include_inactive BOOLEAN,
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
        SELECT sp.id AS project_id, sp.created_at, count(*) OVER () AS total_count
        FROM projects sp
        WHERE (p_include_inactive OR sp.is_active = true)
          AND (
              EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
              OR EXISTS (
                  SELECT 1 FROM project_members pm
                  WHERE pm.project_id = sp.id
                    AND pm.user_id = p_user_id
                    AND (sp.is_active = true OR sp.owner_id = p_user_id)
              )
          )
        ORDER BY sp.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT
        p AS project,
        (SELECT count(*) FROM project_members pm WHERE pm.project_id = p.id) AS member_count,
        (SELECT count(*) FROM tasks t WHERE t.project_id = p.id AND t.status = 'todo' AND t.is_active = true)
            AS task_count_todo,
        (SELECT count(*) FROM tasks t WHERE t.project_id = p.id AND t.status = 'in_progress' AND t.is_active = true)
            AS task_count_in_progress,
        (SELECT count(*) FROM tasks t WHERE t.project_id = p.id AND t.status = 'done' AND t.is_active = true)
            AS task_count_done,
        s.total_count
    FROM scoped s
    JOIN projects p ON p.id = s.project_id
    ORDER BY p.created_at DESC;
$$;

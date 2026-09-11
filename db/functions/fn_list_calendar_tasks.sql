CREATE OR REPLACE FUNCTION fn_list_calendar_tasks(
    p_user_id UUID,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ,
    p_scope VARCHAR,
    p_project_id UUID DEFAULT NULL
)
RETURNS TABLE (task tasks, project_is_active BOOLEAN)
LANGUAGE sql
STABLE
AS $$
    SELECT t, p.is_active
      FROM tasks AS t
      LEFT JOIN projects AS p ON p.id = t.project_id
     WHERE t.is_active = true
       AND t.due_at IS NOT NULL
       AND t.due_at >= p_from
       AND t.due_at < p_to
       AND (
            (p_scope = 'me' AND ((t.project_id IS NULL AND t.created_by = p_user_id) OR t.assignee_id = p_user_id))
            OR (p_scope = 'project' AND t.project_id = p_project_id)
       )
     ORDER BY t.due_at ASC, t.id ASC;
$$;

CREATE OR REPLACE FUNCTION fn_list_tasks(
    p_user_id UUID,
    p_project_id UUID,
    p_status VARCHAR,
    p_include_inactive BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF tasks
LANGUAGE sql
STABLE
AS $$
    SELECT t.*
    FROM tasks t
    WHERE (p_include_inactive OR t.is_active = true)
      AND (p_status IS NULL OR t.status = p_status)
      AND (
          (
              p_project_id IS NULL
              AND (
                  (t.project_id IS NULL AND t.created_by = p_user_id)
                  OR (
                      t.project_id IS NOT NULL
                      AND (
                          EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
                          OR EXISTS (
                              SELECT 1 FROM project_members pm
                              WHERE pm.project_id = t.project_id AND pm.user_id = p_user_id
                          )
                      )
                  )
              )
          )
          OR (
              p_project_id IS NOT NULL
              AND t.project_id = p_project_id
              AND (
                  EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
                  OR EXISTS (
                      SELECT 1 FROM project_members pm
                      WHERE pm.project_id = p_project_id AND pm.user_id = p_user_id
                  )
              )
          )
      )
    ORDER BY t.created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

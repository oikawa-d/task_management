CREATE OR REPLACE FUNCTION fn_count_tasks(
    p_user_id UUID,
    p_project_id UUID,
    p_status VARCHAR,
    p_include_inactive BOOLEAN,
    p_unassigned BOOLEAN
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM tasks t
    WHERE (p_include_inactive OR t.is_active = true)
      AND (p_status IS NULL OR t.status = p_status)
      AND (
          (
              p_project_id IS NULL
              AND p_unassigned = true
              AND t.project_id IS NULL
              AND (
                  EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
                  OR t.created_by = p_user_id
              )
          )
          OR (
              p_project_id IS NULL
              AND p_unassigned = false
              AND (
                  (
                      t.project_id IS NULL
                      AND (
                          EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
                          OR t.created_by = p_user_id
                      )
                  )
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
      );
$$;

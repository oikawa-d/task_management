CREATE OR REPLACE FUNCTION fn_is_project_member(
    p_project_id UUID,
    p_user_id UUID
) RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM users u
        WHERE u.id = p_user_id
          AND u.is_active = true
          AND (
              u.role = 'admin'
              OR EXISTS (
                  SELECT 1
                  FROM project_members pm
                  WHERE pm.project_id = p_project_id
                    AND pm.user_id = p_user_id
              )
          )
    );
$$;

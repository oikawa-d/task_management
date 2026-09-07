CREATE OR REPLACE PROCEDURE sp_add_project_member(
    p_project_id UUID,
    p_user_id UUID,
    p_invited_by UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM project_members WHERE project_id = p_project_id AND user_id = p_user_id
    ) THEN
        RAISE EXCEPTION 'user is already a project member' USING ERRCODE = 'P0003';
    END IF;

    INSERT INTO project_members (project_id, user_id, invited_by)
    VALUES (p_project_id, p_user_id, p_invited_by);
END;
$$;

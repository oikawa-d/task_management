CREATE OR REPLACE PROCEDURE sp_remove_project_member(
    p_project_id UUID,
    p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM projects WHERE id = p_project_id AND owner_id = p_user_id
    ) THEN
        RAISE EXCEPTION 'owner cannot be removed from project' USING ERRCODE = 'P0004';
    END IF;

    UPDATE tasks SET assignee_id = NULL WHERE project_id = p_project_id AND assignee_id = p_user_id;

    DELETE FROM project_members WHERE project_id = p_project_id AND user_id = p_user_id;
END;
$$;

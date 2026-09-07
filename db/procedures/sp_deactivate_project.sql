CREATE OR REPLACE PROCEDURE sp_deactivate_project(
    p_project_id UUID,
    p_is_active BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE projects SET is_active = p_is_active WHERE id = p_project_id;
END;
$$;

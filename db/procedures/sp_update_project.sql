CREATE OR REPLACE PROCEDURE sp_update_project(
    p_project_id UUID,
    p_name VARCHAR,
    p_description TEXT,
    p_start_at TIMESTAMPTZ,
    p_end_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_start_at IS NOT NULL AND p_end_at IS NOT NULL AND p_end_at < p_start_at THEN
        RAISE EXCEPTION 'end_at must not be before start_at' USING ERRCODE = 'P0009';
    END IF;

    UPDATE projects
       SET name = p_name,
           description = p_description,
           start_at = p_start_at,
           end_at = p_end_at
     WHERE id = p_project_id;
END;
$$;

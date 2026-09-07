CREATE OR REPLACE PROCEDURE sp_create_task(
    p_project_id UUID,
    p_created_by UUID,
    p_assignee_id UUID,
    p_title VARCHAR,
    p_body TEXT,
    p_status VARCHAR,
    p_due_at TIMESTAMPTZ,
    p_position INTEGER,
    OUT p_task_id UUID
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_lock_key TEXT;
    v_position INTEGER;
BEGIN
    v_lock_key := COALESCE(p_project_id::text, '00000000-0000-0000-0000-000000000000') || ':' || p_status;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_lock_key, 0));

    IF p_position IS NULL THEN
        v_position := fn_next_task_position(p_project_id, p_status);
    ELSE
        v_position := p_position;
    END IF;

    INSERT INTO tasks (project_id, created_by, assignee_id, title, description, status, due_at, position)
    VALUES (p_project_id, p_created_by, p_assignee_id, p_title, p_body, p_status, p_due_at, v_position)
    RETURNING id INTO p_task_id;
END;
$$;

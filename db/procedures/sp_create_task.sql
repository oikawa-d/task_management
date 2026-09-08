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
    IF p_assignee_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM users WHERE id = p_assignee_id AND is_active = true) THEN
        RAISE EXCEPTION 'assignee is not an active user' USING ERRCODE = 'P0006';
    END IF;

    v_lock_key := COALESCE(p_project_id::text, '00000000-0000-0000-0000-000000000000') || ':' || p_status;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_lock_key, 0));

    IF p_position IS NULL THEN
        v_position := fn_next_task_position(p_project_id, p_status);
    ELSE
        v_position := p_position;
        -- 明示的なposition指定時は、既存タスクの挿入位置以降を+1でずらして空きを作る
        UPDATE tasks
           SET position = position + 1
         WHERE project_id IS NOT DISTINCT FROM p_project_id
           AND status = p_status
           AND position >= v_position;
    END IF;

    INSERT INTO tasks (project_id, created_by, assignee_id, title, description, status, due_at, position)
    VALUES (p_project_id, p_created_by, p_assignee_id, p_title, p_body, p_status, p_due_at, v_position)
    RETURNING id INTO p_task_id;

    IF p_assignee_id IS NOT NULL
       AND p_due_at IS NOT NULL
       AND p_due_at::date = CURRENT_DATE THEN
        INSERT INTO notifications (user_id, task_id, type, title, body, due_at, dedupe_key)
        VALUES (
            p_assignee_id,
            p_task_id,
            'due_today_created',
            p_title,
            p_body,
            p_due_at,
            'created:' || p_task_id::text
        )
        ON CONFLICT (user_id, dedupe_key) DO NOTHING;
    END IF;
END;
$$;

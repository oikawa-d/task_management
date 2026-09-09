CREATE OR REPLACE PROCEDURE sp_update_task(
    p_task_id UUID,
    p_editor_id UUID,
    p_version INTEGER,
    p_title VARCHAR,
    p_body TEXT,
    p_status VARCHAR,
    p_assignee_id UUID,
    p_due_at TIMESTAMPTZ,
    p_position INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_project_id UUID;
    v_old_status VARCHAR;
    v_old_position INTEGER;
    v_old_version INTEGER;
    v_new_position INTEGER;
    v_status_changed BOOLEAN;
    v_old_key TEXT;
    v_new_key TEXT;
    v_placeholder CONSTANT TEXT := '00000000-0000-0000-0000-000000000000';
BEGIN
    SELECT project_id, status, position, version
      INTO v_project_id, v_old_status, v_old_position, v_old_version
      FROM tasks
     WHERE id = p_task_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF v_old_version <> p_version THEN
        RAISE EXCEPTION 'task version conflict' USING ERRCODE = 'P0005';
    END IF;

    IF p_assignee_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM users WHERE id = p_assignee_id AND is_active = true) THEN
        RAISE EXCEPTION 'assignee is not an active user' USING ERRCODE = 'P0006';
    END IF;

    v_status_changed := (p_status IS DISTINCT FROM v_old_status);

    IF v_status_changed THEN
        v_old_key := COALESCE(v_project_id::text, v_placeholder) || ':' || v_old_status;
        v_new_key := COALESCE(v_project_id::text, v_placeholder) || ':' || p_status;

        IF v_old_key <= v_new_key THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));
            PERFORM pg_advisory_xact_lock(hashtextextended(v_new_key, 0));
        ELSE
            PERFORM pg_advisory_xact_lock(hashtextextended(v_new_key, 0));
            PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));
        END IF;

        -- 旧列：移動対象より後続のpositionを-1で詰める
        UPDATE tasks
           SET position = position - 1
         WHERE project_id IS NOT DISTINCT FROM v_project_id
           AND status = v_old_status
           AND position > v_old_position;

        IF p_position IS NULL THEN
            v_new_position := fn_next_task_position(v_project_id, p_status);
        ELSE
            v_new_position := p_position;
            -- 新列：挿入位置以降を+1でずらして空きを作る
            UPDATE tasks
               SET position = position + 1
             WHERE project_id IS NOT DISTINCT FROM v_project_id
               AND status = p_status
               AND position >= v_new_position;
        END IF;
    ELSIF p_position IS NOT NULL AND p_position <> v_old_position THEN
        v_old_key := COALESCE(v_project_id::text, v_placeholder) || ':' || v_old_status;
        PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));

        IF p_position > v_old_position THEN
            UPDATE tasks
               SET position = position - 1
             WHERE project_id IS NOT DISTINCT FROM v_project_id
               AND status = v_old_status
               AND position > v_old_position
               AND position <= p_position
               AND id <> p_task_id;
        ELSE
            UPDATE tasks
               SET position = position + 1
             WHERE project_id IS NOT DISTINCT FROM v_project_id
               AND status = v_old_status
               AND position >= p_position
               AND position < v_old_position
               AND id <> p_task_id;
        END IF;
        v_new_position := p_position;
    ELSE
        v_new_position := v_old_position;
    END IF;

    UPDATE tasks
       SET title = p_title,
           description = p_body,
           status = p_status,
           assignee_id = p_assignee_id,
           due_at = p_due_at,
           position = v_new_position,
           version = version + 1
     WHERE id = p_task_id
       AND version = p_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'task version conflict' USING ERRCODE = 'P0005';
    END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE sp_deactivate_task(
    p_task_id UUID,
    p_is_active BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- position/status は変更しない（compaction を行わない）。
    UPDATE tasks
       SET is_active = p_is_active,
           version = version + 1
     WHERE id = p_task_id;
END;
$$;

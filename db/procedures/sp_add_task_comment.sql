CREATE OR REPLACE PROCEDURE sp_add_task_comment(
    p_task_id UUID,
    p_user_id UUID,
    p_body TEXT,
    OUT p_comment_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO task_comments (task_id, user_id, body)
    VALUES (p_task_id, p_user_id, p_body)
    RETURNING id INTO p_comment_id;
END;
$$;

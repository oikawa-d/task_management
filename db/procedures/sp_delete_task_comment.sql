CREATE OR REPLACE PROCEDURE sp_delete_task_comment(
    p_comment_id UUID,
    p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- 投稿者本人かどうかの検証はAPI層の責務のため、本SPでは行わない。
    DELETE FROM task_comments WHERE id = p_comment_id;
END;
$$;

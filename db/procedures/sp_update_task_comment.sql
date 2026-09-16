CREATE OR REPLACE PROCEDURE sp_update_task_comment(
    p_comment_id UUID,
    p_user_id UUID,
    p_body TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- 投稿者本人かどうかの検証はAPI層の責務のため、本SPでは行わない。
    UPDATE task_comments SET body = p_body WHERE id = p_comment_id;
END;
$$;

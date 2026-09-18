-- 概要: タスクコメントの本文を更新する。投稿者本人かどうかの検証はAPI層の責務であり、本プロシージャでは行わない。
-- 引数: p_comment_id UUID — 更新対象コメントID / p_user_id UUID — 更新を要求したユーザーID（本SP内では未使用） / p_body TEXT — 更新後の本文
-- 戻り値: なし
-- 副作用: task_commentsテーブルのbodyをUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
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

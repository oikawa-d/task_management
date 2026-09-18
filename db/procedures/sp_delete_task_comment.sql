-- 概要: タスクコメントを削除する。投稿者本人かどうかの検証はAPI層の責務であり、本プロシージャでは行わない。
-- 引数: p_comment_id UUID — 削除対象コメントID / p_user_id UUID — 削除を要求したユーザーID（本SP内では未使用）
-- 戻り値: なし
-- 副作用: task_commentsテーブルからDELETE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
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

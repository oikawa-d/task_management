-- 概要: タスクへコメントを1件追加する。
-- 引数: p_task_id UUID — コメント対象タスクID / p_user_id UUID — 投稿者ユーザーID / p_body TEXT — コメント本文
-- 戻り値: p_comment_id UUID — 追加されたコメントのID
-- 副作用: task_commentsテーブルへINSERT。COMMIT/ROLLBACKは本プロシージャ内では行わない。
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

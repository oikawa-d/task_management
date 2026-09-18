-- 概要: 指定ユーザーの未読通知をすべて既読にする。
-- 引数: p_user_id UUID — 対象ユーザーID
-- 戻り値: p_updated_count INTEGER — 既読へ更新した通知件数
-- 副作用: notificationsテーブルのread_atをUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_mark_all_notifications_read(
    p_user_id UUID,
    OUT p_updated_count INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE notifications
       SET read_at = now()
     WHERE user_id = p_user_id
       AND read_at IS NULL;

    GET DIAGNOSTICS p_updated_count = ROW_COUNT;
END;
$$;

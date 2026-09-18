-- 概要: 指定ユーザーの通知1件を既読にする。既に既読の場合はread_atを変更せず、対象が存在しない場合はNULLを返す。
-- 引数: p_notification_id UUID — 対象通知ID / p_user_id UUID — 通知の所有ユーザーID
-- 戻り値: p_read_at TIMESTAMPTZ — 既読日時（対象が存在しない場合はNULL）
-- 副作用: notificationsテーブルの対象行をFOR UPDATEでロックし、read_atが未設定の場合のみUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_mark_notification_read(
    p_notification_id UUID,
    p_user_id UUID,
    OUT p_read_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    SELECT read_at
      INTO p_read_at
      FROM notifications
     WHERE id = p_notification_id
       AND user_id = p_user_id
     FOR UPDATE;

    IF NOT FOUND THEN
        p_read_at := NULL;
        RETURN;
    END IF;

    UPDATE notifications
       SET read_at = COALESCE(read_at, now())
     WHERE id = p_notification_id
       AND user_id = p_user_id;

    SELECT read_at
      INTO p_read_at
      FROM notifications
     WHERE id = p_notification_id
       AND user_id = p_user_id;
END;
$$;

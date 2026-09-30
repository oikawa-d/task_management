-- 状態: 現役（根拠: alembic api/alembic/versions/0023_return_notification_read_results.py の
--       downgrade() から参照される。同名の現役オブジェクトが db/procedures/sp_mark_all_notifications_read.sql に存在する）
-- 概要: ユーザーの未読通知を一括で既読にする。更新件数を返さない、現行版より前の版。
-- 引数: p_user_id UUID — 対象ユーザーID
-- 戻り値: なし
-- 副作用: notificationsテーブルの、対象ユーザーの未読行(read_at IS NULL)すべてのread_atを現在時刻でUPDATEする。
CREATE OR REPLACE PROCEDURE sp_mark_all_notifications_read(
    p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE notifications
       SET read_at = now()
     WHERE user_id = p_user_id
       AND read_at IS NULL;
END;
$$;

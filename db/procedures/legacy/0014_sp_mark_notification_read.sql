-- 状態: 現役（根拠: alembic api/alembic/versions/0021_update_sp_mark_notification_read_return_value.py の
--       downgrade() から参照される。同名の現役オブジェクトが db/procedures/sp_mark_notification_read.sql に存在する）
-- 概要: 通知を既読にする。既読日時を戻さない、OUT引数導入前の版。
-- 引数: p_notification_id UUID — 対象通知ID
--       p_user_id UUID — 通知の所有ユーザーID（本人の通知のみ更新対象）
-- 戻り値: なし
-- 副作用: notificationsテーブルの対象行のread_atを、未設定の場合のみ現在時刻でUPDATEする。
CREATE OR REPLACE PROCEDURE sp_mark_notification_read(
    p_notification_id UUID,
    p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE notifications
       SET read_at = COALESCE(read_at, now())
     WHERE id = p_notification_id
       AND user_id = p_user_id;
END;
$$;

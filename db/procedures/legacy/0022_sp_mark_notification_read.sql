-- 状態: 現役（根拠: alembic api/alembic/versions/0023_return_notification_read_results.py の
--       downgrade() から参照される。同名の現役オブジェクトが db/procedures/sp_mark_notification_read.sql に存在する）
-- 概要: 通知を既読にし、既読日時を返す。対象が存在しない場合の分岐を持たない、現行版より前の版。
--       UPDATE ... RETURNING で既読日時をそのままOUT引数に設定する。
-- 引数: p_notification_id UUID — 対象通知ID
--       p_user_id UUID — 通知の所有ユーザーID（本人の通知のみ更新対象）
--       OUT p_read_at TIMESTAMPTZ — 更新後の既読日時（対象行が無い場合はUPDATEが0件になりNULLのまま）
-- 戻り値: なし（OUT引数 p_read_at に既読日時を設定）
-- 副作用: notificationsテーブルの対象行のread_atを、未設定の場合のみ現在時刻でUPDATEする。
CREATE OR REPLACE PROCEDURE sp_mark_notification_read(
    p_notification_id UUID,
    p_user_id UUID,
    OUT p_read_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE notifications
       SET read_at = COALESCE(read_at, now())
     WHERE id = p_notification_id
       AND user_id = p_user_id
     RETURNING read_at INTO p_read_at;
END;
$$;

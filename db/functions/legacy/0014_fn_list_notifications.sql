-- 状態: 現役（根拠: alembic api/alembic/versions/0019_update_fn_list_notifications_return_type.py の
--       downgrade() から参照される。同名の現役オブジェクトが db/functions/fn_list_notifications.sql に存在する）
-- 概要: 通知一覧を取得する。戻り値をSETOF notificationsとする、返り値型変更前の版。
-- 引数: p_user_id UUID — 通知の所有ユーザーID
--       p_unread_only BOOLEAN — 未読のみに絞り込むか
--       p_limit INTEGER — 取得件数上限
--       p_offset INTEGER — 取得開始位置
-- 戻り値: SETOF notifications — 条件に合致する通知レコード
-- 副作用: なし
CREATE OR REPLACE FUNCTION fn_list_notifications(
    p_user_id UUID,
    p_unread_only BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF notifications
LANGUAGE sql
STABLE
AS $$
    SELECT n.*
    FROM notifications n
    WHERE n.user_id = p_user_id
      AND (p_unread_only = false OR n.read_at IS NULL)
    ORDER BY n.created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

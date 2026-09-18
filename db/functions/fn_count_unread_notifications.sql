-- 概要: 指定ユーザーの未読通知件数を算出する
-- 引数: p_user_id UUID — 対象ユーザーID
-- 戻り値: BIGINT — 未読通知の件数
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/service/notification_service.py, api/app/repository/notification_repository.py
CREATE OR REPLACE FUNCTION fn_count_unread_notifications(
    p_user_id UUID
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM notifications
    WHERE user_id = p_user_id
      AND read_at IS NULL;
$$;

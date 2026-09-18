-- 概要: 指定ユーザーの通知件数を、未読のみに限定するかどうかを指定して算出する
-- 引数: p_user_id UUID — 対象ユーザーID／p_unread_only BOOLEAN — trueの場合は未読通知のみを対象にする
-- 戻り値: BIGINT — 条件に合致する通知の件数
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/notification_repository.py
CREATE OR REPLACE FUNCTION fn_count_notifications(
    p_user_id UUID,
    p_unread_only BOOLEAN
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM notifications n
    WHERE n.user_id = p_user_id
      AND (p_unread_only = false OR n.read_at IS NULL);
$$;

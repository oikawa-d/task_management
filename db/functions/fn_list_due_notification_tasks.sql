-- 概要: 期限超過通知バッチ向けに、担当者が設定済みで未完了かつ期限が閾値時刻より前の有効タスクを列挙する
-- 引数: p_threshold TIMESTAMPTZ — この時刻より期限が前のタスクを対象にする
-- 戻り値: SETOF tasks — 通知対象タスクの行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: batchの期限超過通知処理（api/alembic/versions/0014_create_notification_history_functions_and_triggers.py）
CREATE OR REPLACE FUNCTION fn_list_due_notification_tasks(
    p_threshold TIMESTAMPTZ
) RETURNS SETOF tasks
LANGUAGE sql
STABLE
AS $$
    SELECT *
    FROM tasks
    WHERE due_at < p_threshold
      AND is_active = true
      AND assignee_id IS NOT NULL
      AND status != 'done';
$$;

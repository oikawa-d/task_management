-- 概要: 指定ユーザーの通知一覧を未読限定・ページングで取得し、関連タスクのタイトル・プロジェクトIDと全件数を付与して返す
-- 引数: p_user_id UUID — 対象ユーザーID／p_unread_only BOOLEAN — trueの場合は未読通知のみ対象／p_limit INTEGER — 取得件数上限／p_offset INTEGER — 取得開始位置
-- 戻り値: TABLE(notification notifications, task_title VARCHAR, task_project_id UUID, total_count BIGINT) — 通知行と関連タスク情報、絞り込み後の全件数
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/notification_repository.py, api/app/service/notification_service.py
CREATE OR REPLACE FUNCTION fn_list_notifications(
    p_user_id UUID,
    p_unread_only BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    notification notifications,
    task_title VARCHAR,
    task_project_id UUID,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT n.id, count(*) OVER () AS total_count
        FROM notifications n
        WHERE n.user_id = p_user_id
          AND (p_unread_only = false OR n.read_at IS NULL)
        ORDER BY n.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT
        n AS notification,
        t.title AS task_title,
        t.project_id AS task_project_id,
        s.total_count
    FROM scoped s
    JOIN notifications n ON n.id = s.id
    LEFT JOIN tasks t ON t.id = n.task_id
    ORDER BY n.created_at DESC;
$$;

-- 概要: カレンダー表示向けに、期限日が指定期間内の有効タスクを「自分のタスク」または「指定プロジェクトのタスク」の範囲で取得する
-- 引数: p_user_id UUID — 呼び出しユーザーID（p_scope='me'時の対象判定に使用）／p_from TIMESTAMPTZ — 期限日の検索期間開始／p_to TIMESTAMPTZ — 期限日の検索期間終了／p_scope VARCHAR — 'me'（自分に関連するタスク）または'project'（指定プロジェクトのタスク）／p_project_id UUID — p_scope='project'時の対象プロジェクト（省略時NULL）
-- 戻り値: TABLE(task tasks, project_is_active BOOLEAN, comment_count BIGINT) — 期限日昇順のタスク行と付帯情報
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/task_repository.py
CREATE OR REPLACE FUNCTION fn_list_calendar_tasks(
    p_user_id UUID,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ,
    p_scope VARCHAR,
    p_project_id UUID DEFAULT NULL
)
RETURNS TABLE (task tasks, project_is_active BOOLEAN, comment_count BIGINT)
LANGUAGE sql
STABLE
AS $$
    WITH comment_counts AS (
        SELECT task_id, count(*) AS comment_count
        FROM task_comments
        GROUP BY task_id
    )
    SELECT t, p.is_active, COALESCE(cc.comment_count, 0)
      FROM tasks AS t
      LEFT JOIN projects AS p ON p.id = t.project_id
      LEFT JOIN comment_counts AS cc ON cc.task_id = t.id
     WHERE t.is_active = true
       AND t.due_at IS NOT NULL
       AND t.due_at >= p_from
       AND t.due_at < p_to
       AND (
            (p_scope = 'me' AND ((t.project_id IS NULL AND t.created_by = p_user_id) OR t.assignee_id = p_user_id))
            OR (p_scope = 'project' AND t.project_id = p_project_id)
       )
     ORDER BY t.due_at ASC, t.id ASC;
$$;

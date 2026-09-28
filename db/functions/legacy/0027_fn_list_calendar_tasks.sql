-- 状態: 現役（根拠: alembic api/alembic/versions/0028_align_task_api_contracts.py の downgrade() で
--       DB_DIR / "functions/legacy" / f"0027_{filename}" として動的に参照される
--       （filenameに"fn_list_calendar_tasks.sql"を含むループ）。
--       同名の現役オブジェクトが db/functions/fn_list_calendar_tasks.sql に存在する）
-- 概要: カレンダー表示用に、期限(due_at)が指定期間内にある有効なタスク一覧を取得する。契約統一前の版。
-- 引数: p_user_id UUID — 参照者のユーザーID（p_scope='me'指定時の絞り込みに使用）
--       p_from TIMESTAMPTZ — 期限の検索期間開始（以上）
--       p_to TIMESTAMPTZ — 期限の検索期間終了（未満）
--       p_scope VARCHAR — 'me'（自分が作成した個人タスクまたは担当タスク）または
--                         'project'（p_project_idで指定したプロジェクトのタスク）
--       p_project_id UUID DEFAULT NULL — p_scope='project'時の対象プロジェクトID
-- 戻り値: TABLE(task tasks, project_is_active BOOLEAN) — 条件に合致するタスク本体と、
--       そのプロジェクトの有効状態
-- 副作用: なし
CREATE OR REPLACE FUNCTION fn_list_calendar_tasks(
    p_user_id UUID, p_from TIMESTAMPTZ, p_to TIMESTAMPTZ, p_scope VARCHAR, p_project_id UUID DEFAULT NULL
)
RETURNS TABLE (task tasks, project_is_active BOOLEAN)
LANGUAGE sql STABLE AS $$
    SELECT t, p.is_active FROM tasks t LEFT JOIN projects p ON p.id = t.project_id
    WHERE t.is_active = true AND t.due_at IS NOT NULL AND t.due_at >= p_from AND t.due_at < p_to
      AND ((p_scope = 'me' AND ((t.project_id IS NULL AND t.created_by = p_user_id) OR t.assignee_id = p_user_id))
           OR (p_scope = 'project' AND t.project_id = p_project_id))
    ORDER BY t.due_at ASC, t.id ASC;
$$;

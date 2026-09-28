-- 状態: 現役（根拠: alembic api/alembic/versions/0010_create_project_task_functions_and_triggers.py の
--       upgrade()、および 0025_add_unassigned_filter_to_task_function.py の downgrade() から参照される）
-- 概要: タスク一覧を取得する。担当外(unassigned)フィルタ導入前の版で、
--       プロジェクト所属・作成者・管理者権限に基づくアクセス制御のうえ、
--       ステータス・有効/無効・ページングで絞り込む。
-- 引数: p_user_id UUID — 参照者のユーザーID（権限判定に使用）
--       p_project_id UUID — 絞り込み対象プロジェクトID（NULLで個人タスクも対象）
--       p_status VARCHAR — ステータス絞り込み（NULLで全件）
--       p_include_inactive BOOLEAN — 無効化済みタスクを含めるか
--       p_limit INTEGER — 取得件数上限
--       p_offset INTEGER — 取得開始位置
-- 戻り値: TABLE(task tasks, project_is_active BOOLEAN) — 条件に合致するタスク本体と、
--       そのプロジェクトの有効状態
-- 副作用: なし
CREATE OR REPLACE FUNCTION fn_list_tasks(
    p_user_id UUID,
    p_project_id UUID,
    p_status VARCHAR,
    p_include_inactive BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    task tasks,
    project_is_active BOOLEAN
)
LANGUAGE sql
STABLE
AS $$
    SELECT t, p.is_active
    FROM tasks t
    LEFT JOIN projects p ON p.id = t.project_id
    WHERE (p_include_inactive OR t.is_active = true)
      AND (p_status IS NULL OR t.status = p_status)
      AND (
          (
              p_project_id IS NULL
              AND (
                  (
                      t.project_id IS NULL
                      AND (
                          EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
                          OR t.created_by = p_user_id
                      )
                  )
                  OR (
                      t.project_id IS NOT NULL
                      AND (
                          EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
                          OR EXISTS (
                              SELECT 1 FROM project_members pm
                              WHERE pm.project_id = t.project_id AND pm.user_id = p_user_id
                          )
                      )
                  )
              )
          )
          OR (
              p_project_id IS NOT NULL
              AND t.project_id = p_project_id
              AND (
                  EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
                  OR EXISTS (
                      SELECT 1 FROM project_members pm
                      WHERE pm.project_id = p_project_id AND pm.user_id = p_user_id
                  )
              )
          )
      )
    ORDER BY t.created_at DESC
    LIMIT p_limit OFFSET p_offset;
$$;

-- 概要: 呼び出しユーザーが閲覧権限を持つタスクを対象に、プロジェクト・ステータス・未所属タスク条件で絞り込んだ件数を算出する
-- 引数: p_user_id UUID — 権限判定・作成者判定に使う呼び出しユーザーID／p_project_id UUID — 対象プロジェクト（NULLでプロジェクト横断）／p_status VARCHAR — ステータスで絞り込み（NULLで無視）／p_include_inactive BOOLEAN — 無効タスクも含めるか／p_unassigned BOOLEAN — プロジェクト未所属タスクのみを対象にするか（p_project_idがNULLの場合のみ意味を持つ）
-- 戻り値: BIGINT — 権限・条件に合致するタスクの件数
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/task_repository.py
CREATE OR REPLACE FUNCTION fn_count_tasks(
    p_user_id UUID,
    p_project_id UUID,
    p_status VARCHAR,
    p_include_inactive BOOLEAN,
    p_unassigned BOOLEAN
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM tasks t
    WHERE (p_include_inactive OR t.is_active = true)
      AND (p_status IS NULL OR t.status = p_status)
      AND (
          (
              p_project_id IS NULL
              AND p_unassigned = true
              AND t.project_id IS NULL
              AND (
                  EXISTS (SELECT 1 FROM users u WHERE u.id = p_user_id AND u.role = 'admin')
                  OR t.created_by = p_user_id
              )
          )
          OR (
              p_project_id IS NULL
              AND p_unassigned = false
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
      );
$$;

-- 概要: 指定プロジェクトのカンバンボード表示用に、タスク一覧とプロジェクト有効状態・コメント数を付与して返す
-- 引数: p_project_id UUID — 対象プロジェクトID／p_include_inactive BOOLEAN — 無効タスクも含めるか
-- 戻り値: TABLE(task tasks, project_is_active BOOLEAN, comment_count BIGINT) — ステータス・並び順でソートされたタスク行とその付帯情報
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/task_repository.py
CREATE OR REPLACE FUNCTION fn_get_project_board(
    p_project_id UUID,
    p_include_inactive BOOLEAN
) RETURNS TABLE (
    task tasks,
    project_is_active BOOLEAN,
    comment_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH comment_counts AS (
        SELECT task_id, count(*) AS comment_count
        FROM task_comments
        GROUP BY task_id
    )
    SELECT t, p.is_active, COALESCE(cc.comment_count, 0)
    FROM tasks t
    LEFT JOIN projects p ON p.id = t.project_id
    LEFT JOIN comment_counts cc ON cc.task_id = t.id
    WHERE t.project_id = p_project_id
      AND (p_include_inactive OR t.is_active = true)
    ORDER BY t.status, t.position;
$$;

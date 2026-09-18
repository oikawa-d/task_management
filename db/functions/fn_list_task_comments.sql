-- 概要: 指定タスクのコメント一覧を作成日時の昇順で取得する
-- 引数: p_task_id UUID — 対象タスクID
-- 戻り値: SETOF task_comments — 作成日時昇順のコメント行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/task_comment_repository.py
CREATE OR REPLACE FUNCTION fn_list_task_comments(
    p_task_id UUID
) RETURNS SETOF task_comments
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM task_comments
    WHERE task_id = p_task_id
    ORDER BY created_at ASC;
$$;

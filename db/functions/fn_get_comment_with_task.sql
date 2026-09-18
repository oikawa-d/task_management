-- 概要: IDを指定してタスクコメント1件を取得する
-- 引数: p_comment_id UUID — 取得対象のコメントID
-- 戻り値: SETOF task_comments — 合致するコメント行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/task_comment_repository.py
CREATE OR REPLACE FUNCTION fn_get_comment_with_task(
    p_comment_id UUID
) RETURNS SETOF task_comments
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM task_comments WHERE id = p_comment_id;
$$;

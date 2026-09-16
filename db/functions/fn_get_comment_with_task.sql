CREATE OR REPLACE FUNCTION fn_get_comment_with_task(
    p_comment_id UUID
) RETURNS SETOF task_comments
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM task_comments WHERE id = p_comment_id;
$$;

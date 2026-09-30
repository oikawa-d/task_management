-- 状態: 現役（根拠: alembic api/alembic/versions/0010_create_project_task_functions_and_triggers.py の
--       upgrade()、および 0016_update_task_notification_procedures.py の downgrade() から参照される。
--       同名の現役オブジェクトが db/procedures/sp_create_task.sql に存在する）
-- 概要: タスクを新規作成する。通知発行導入前の版。担当者が有効ユーザーであることを検証し、
--       同一プロジェクト・ステータス列のロックを取得したうえで、
--       指定位置(position)が未指定なら末尾へ、指定ありなら既存タスクをずらして挿入する。
-- 引数: p_project_id UUID — 所属プロジェクトID（NULLで個人タスク）
--       p_created_by UUID — 作成者のユーザーID
--       p_assignee_id UUID — 担当者のユーザーID（NULLで未割当）
--       p_title VARCHAR — タスクタイトル
--       p_body TEXT — タスク本文（tasks.descriptionに格納）
--       p_status VARCHAR — 初期ステータス
--       p_due_at TIMESTAMPTZ — 期限日時（NULLで未設定）
--       p_position INTEGER — 挿入位置（NULLで同一列の末尾に自動採番）
--       OUT p_task_id UUID — 作成したタスクのID
-- 戻り値: なし（OUT引数 p_task_id に作成したタスクIDを設定）
-- 副作用: tasksテーブルへのINSERT。p_position指定時はtasksテーブルの同一プロジェクト・
--       ステータス列で挿入位置以降のposition値をUPDATEでずらす。
CREATE OR REPLACE PROCEDURE sp_create_task(
    p_project_id UUID,
    p_created_by UUID,
    p_assignee_id UUID,
    p_title VARCHAR,
    p_body TEXT,
    p_status VARCHAR,
    p_due_at TIMESTAMPTZ,
    p_position INTEGER,
    OUT p_task_id UUID
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_lock_key TEXT;
    v_position INTEGER;
BEGIN
    IF p_assignee_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM users WHERE id = p_assignee_id AND is_active = true) THEN
        RAISE EXCEPTION 'assignee is not an active user' USING ERRCODE = 'P0006';
    END IF;

    v_lock_key := COALESCE(p_project_id::text, '00000000-0000-0000-0000-000000000000') || ':' || p_status;
    PERFORM pg_advisory_xact_lock(hashtextextended(v_lock_key, 0));

    IF p_position IS NULL THEN
        v_position := fn_next_task_position(p_project_id, p_status);
    ELSE
        v_position := p_position;
        -- 明示的なposition指定時は、既存タスクの挿入位置以降を+1でずらして空きを作る
        UPDATE tasks
           SET position = position + 1
         WHERE project_id IS NOT DISTINCT FROM p_project_id
           AND status = p_status
           AND position >= v_position;
    END IF;

    INSERT INTO tasks (project_id, created_by, assignee_id, title, description, status, due_at, position)
    VALUES (p_project_id, p_created_by, p_assignee_id, p_title, p_body, p_status, p_due_at, v_position)
    RETURNING id INTO p_task_id;
END;
$$;

-- 状態: 現役（根拠: alembic api/alembic/versions/0010_create_project_task_functions_and_triggers.py の
--       upgrade()、および 0016_update_task_notification_procedures.py の downgrade() から参照される。
--       同名の現役オブジェクトが db/procedures/sp_update_task.sql に存在する）
-- 概要: タスクを楽観ロック(version)付きで更新する。通知発行導入前の版。
--       ステータス変更時は旧列・新列双方のロックを取得して詰め直し・挿入位置調整を行い、
--       同一列内でのposition変更時も影響範囲のposition値を調整する。
--       対象タスクが存在しない場合は何もせずRETURNし、versionが一致しない場合は例外を送出する。
-- 引数: p_task_id UUID — 更新対象のタスクID
--       p_editor_id UUID — 編集者のユーザーID（本版では権限チェックに未使用）
--       p_version INTEGER — 楽観ロック用の現在バージョン
--       p_title VARCHAR — 新しいタイトル
--       p_body TEXT — 新しい本文（tasks.descriptionに格納）
--       p_status VARCHAR — 新しいステータス
--       p_assignee_id UUID — 新しい担当者のユーザーID（NULLで未割当）
--       p_due_at TIMESTAMPTZ — 新しい期限日時
--       p_position INTEGER — 新しい挿入位置（NULLで移動先列の末尾に自動採番）
-- 戻り値: なし
-- 副作用: tasksテーブルの対象行をUPDATE（タイトル・本文・ステータス・担当者・期限・position・version）。
--       ステータス変更やposition変更に伴い、同一プロジェクト・ステータス列内の他タスクのpositionもUPDATEでずらす。
--       担当者が有効ユーザーでない場合、またはversion不一致の場合は例外(P0006/P0005)を送出する。
CREATE OR REPLACE PROCEDURE sp_update_task(
    p_task_id UUID,
    p_editor_id UUID,
    p_version INTEGER,
    p_title VARCHAR,
    p_body TEXT,
    p_status VARCHAR,
    p_assignee_id UUID,
    p_due_at TIMESTAMPTZ,
    p_position INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_project_id UUID;
    v_old_status VARCHAR;
    v_old_position INTEGER;
    v_old_version INTEGER;
    v_new_position INTEGER;
    v_status_changed BOOLEAN;
    v_old_key TEXT;
    v_new_key TEXT;
    v_placeholder CONSTANT TEXT := '00000000-0000-0000-0000-000000000000';
BEGIN
    SELECT project_id, status, position, version
      INTO v_project_id, v_old_status, v_old_position, v_old_version
      FROM tasks
     WHERE id = p_task_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF v_old_version <> p_version THEN
        RAISE EXCEPTION 'task version conflict' USING ERRCODE = 'P0005';
    END IF;

    IF p_assignee_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM users WHERE id = p_assignee_id AND is_active = true) THEN
        RAISE EXCEPTION 'assignee is not an active user' USING ERRCODE = 'P0006';
    END IF;

    v_status_changed := (p_status IS DISTINCT FROM v_old_status);

    IF v_status_changed THEN
        v_old_key := COALESCE(v_project_id::text, v_placeholder) || ':' || v_old_status;
        v_new_key := COALESCE(v_project_id::text, v_placeholder) || ':' || p_status;

        IF v_old_key <= v_new_key THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));
            PERFORM pg_advisory_xact_lock(hashtextextended(v_new_key, 0));
        ELSE
            PERFORM pg_advisory_xact_lock(hashtextextended(v_new_key, 0));
            PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));
        END IF;

        -- 旧列：移動対象より後続のpositionを-1で詰める
        UPDATE tasks
           SET position = position - 1
         WHERE project_id IS NOT DISTINCT FROM v_project_id
           AND status = v_old_status
           AND position > v_old_position;

        IF p_position IS NULL THEN
            v_new_position := fn_next_task_position(v_project_id, p_status);
        ELSE
            v_new_position := p_position;
            -- 新列：挿入位置以降を+1でずらして空きを作る
            UPDATE tasks
               SET position = position + 1
             WHERE project_id IS NOT DISTINCT FROM v_project_id
               AND status = p_status
               AND position >= v_new_position;
        END IF;
    ELSIF p_position IS NOT NULL AND p_position <> v_old_position THEN
        v_old_key := COALESCE(v_project_id::text, v_placeholder) || ':' || v_old_status;
        PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));

        IF p_position > v_old_position THEN
            UPDATE tasks
               SET position = position - 1
             WHERE project_id IS NOT DISTINCT FROM v_project_id
               AND status = v_old_status
               AND position > v_old_position
               AND position <= p_position
               AND id <> p_task_id;
        ELSE
            UPDATE tasks
               SET position = position + 1
             WHERE project_id IS NOT DISTINCT FROM v_project_id
               AND status = v_old_status
               AND position >= p_position
               AND position < v_old_position
               AND id <> p_task_id;
        END IF;
        v_new_position := p_position;
    ELSE
        v_new_position := v_old_position;
    END IF;

    UPDATE tasks
       SET title = p_title,
           description = p_body,
           status = p_status,
           assignee_id = p_assignee_id,
           due_at = p_due_at,
           position = v_new_position,
           version = version + 1
     WHERE id = p_task_id
       AND version = p_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'task version conflict' USING ERRCODE = 'P0005';
    END IF;
END;
$$;

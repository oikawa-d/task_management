-- 概要: タスクを楽観ロック（version一致）で更新する。ステータス変更・position変更に応じて同一ステータス列内の他タスクのpositionを詰め直し、当日期限で担当者がいる場合は期限通知も作成する。対象タスクが存在しない場合は何もせず正常終了する。
-- 引数: p_task_id UUID — 対象タスクID / p_editor_id UUID — 更新者ユーザーID（本SP内では未使用） / p_version INTEGER — 更新前提のバージョン（楽観ロック用） / p_title VARCHAR — タイトル / p_body TEXT — 本文 / p_status VARCHAR — ステータス / p_assignee_id UUID — 担当者ユーザーID（NULL可） / p_due_at TIMESTAMPTZ — 期限日時 / p_position INTEGER — 挿入位置（NULLで末尾自動採番） / p_is_active BOOLEAN — 有効状態（NULLで現状維持） / p_day_start_utc TIMESTAMPTZ — 当日判定の開始境界（UTC） / p_day_end_utc TIMESTAMPTZ — 当日判定の終了境界（UTC）
-- 戻り値: なし
-- 副作用: tasksテーブルの対象行および同一プロジェクト・ステータス内の他タスク行のpositionをUPDATE、対象行のtitle/description/status/assignee_id/due_at/position/is_active/versionをUPDATE（+1）。旧ステータスと新ステータス両方に対しpg_advisory_xact_lockを昇順で取得しdeadlockを回避する。versionが不一致の場合はERRCODE 'P0005'でRAISE EXCEPTIONする。担当者が有効ユーザーでない場合は'P0006'でRAISE EXCEPTIONする。担当者が設定され期限が変更され対象日時範囲内の場合、notificationsテーブルへ'due_today_updated'通知をINSERT（同一dedupe_keyが既存の場合はON CONFLICT DO NOTHING）。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_update_task(
    p_task_id UUID,
    p_editor_id UUID,
    p_version INTEGER,
    p_title VARCHAR,
    p_body TEXT,
    p_status VARCHAR,
    p_assignee_id UUID,
    p_due_at TIMESTAMPTZ,
    p_position INTEGER,
    p_is_active BOOLEAN,
    p_day_start_utc TIMESTAMPTZ,
    p_day_end_utc TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_project_id UUID;
    v_old_status VARCHAR;
    v_old_position INTEGER;
    v_old_version INTEGER;
    v_old_due_at TIMESTAMPTZ;
    v_new_position INTEGER;
    v_status_changed BOOLEAN;
    v_old_key TEXT;
    v_new_key TEXT;
    v_placeholder CONSTANT TEXT := '00000000-0000-0000-0000-000000000000';
BEGIN
    -- Advisory lockは対象行のロックより先に取得する。行ロックを先に取得すると、
    -- 同じ列を並行更新したトランザクションが互いの行を更新しようとしてdeadlockする。
    SELECT project_id, status, position
      INTO v_project_id, v_old_status, v_old_position
      FROM tasks
     WHERE id = p_task_id;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    v_status_changed := (p_status IS DISTINCT FROM v_old_status);

    IF v_status_changed OR (p_position IS NOT NULL AND p_position <> v_old_position) THEN
        v_old_key := COALESCE(v_project_id::text, v_placeholder) || ':' || v_old_status;
        v_new_key := COALESCE(v_project_id::text, v_placeholder) || ':' || p_status;

        IF v_old_key = v_new_key THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));
        ELSIF v_old_key < v_new_key THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));
            PERFORM pg_advisory_xact_lock(hashtextextended(v_new_key, 0));
        ELSE
            PERFORM pg_advisory_xact_lock(hashtextextended(v_new_key, 0));
            PERFORM pg_advisory_xact_lock(hashtextextended(v_old_key, 0));
        END IF;
    END IF;

    SELECT position, version, due_at
      INTO v_old_position, v_old_version, v_old_due_at
      FROM tasks
     WHERE id = p_task_id
     FOR UPDATE;

    IF v_old_version <> p_version THEN
        RAISE EXCEPTION 'task version conflict' USING ERRCODE = 'P0005';
    END IF;

    IF p_assignee_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM users WHERE id = p_assignee_id AND is_active = true) THEN
        RAISE EXCEPTION 'assignee is not an active user' USING ERRCODE = 'P0006';
    END IF;

    v_status_changed := (p_status IS DISTINCT FROM v_old_status);

    IF v_status_changed THEN

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
           is_active = COALESCE(p_is_active, is_active),
           version = version + 1
     WHERE id = p_task_id
       AND version = p_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'task version conflict' USING ERRCODE = 'P0005';
    END IF;

    IF p_assignee_id IS NOT NULL
       AND p_due_at IS NOT NULL
       AND p_due_at IS DISTINCT FROM v_old_due_at
       AND p_due_at >= p_day_start_utc
       AND p_due_at < p_day_end_utc THEN
        INSERT INTO notifications (user_id, task_id, type, title, body, due_at, dedupe_key)
        VALUES (
            p_assignee_id,
            p_task_id,
            'due_today_updated',
            p_title,
            p_body,
            p_due_at,
            'updated:' || p_task_id::text || ':' ||
                to_char(p_due_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
        )
        ON CONFLICT (user_id, dedupe_key) DO NOTHING;
    END IF;
END;
$$;

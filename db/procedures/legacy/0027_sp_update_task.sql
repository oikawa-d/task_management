-- 状態: 現役（根拠: alembic api/alembic/versions/0028_align_task_api_contracts.py の
--       downgrade() で DB_DIR / "procedures/legacy/0027_sp_update_task.sql" として参照される。
--       同名の現役オブジェクトが db/procedures/sp_update_task.sql に存在する）
-- 概要: タスクを楽観ロック(version)付きで更新し、期限が当日範囲内に変更された場合は
--       担当者への通知を発行する。p_is_active引数を持たない、契約統一前の版。
--       ステータス変更やposition変更に伴うアドバイザリロックの取得順序はdeadlock回避のため
--       常に文字列順で固定する。
-- 引数: p_task_id UUID — 更新対象のタスクID
--       p_editor_id UUID — 編集者のユーザーID（本版では権限チェックに未使用）
--       p_version INTEGER — 楽観ロック用の現在バージョン
--       p_title VARCHAR — 新しいタイトル
--       p_body TEXT — 新しい本文（tasks.descriptionに格納）
--       p_status VARCHAR — 新しいステータス
--       p_assignee_id UUID — 新しい担当者のユーザーID（NULLで未割当）
--       p_due_at TIMESTAMPTZ — 新しい期限日時
--       p_position INTEGER — 新しい挿入位置（NULLで移動先列の末尾に自動採番）
--       p_day_start_utc TIMESTAMPTZ — 「当日」とみなす期間の開始（UTC、以上）
--       p_day_end_utc TIMESTAMPTZ — 「当日」とみなす期間の終了（UTC、未満）
-- 戻り値: なし
-- 副作用: tasksテーブルの対象行をUPDATE（タイトル・本文・ステータス・担当者・期限・position・version）。
--       ステータス変更やposition変更に伴い、同一プロジェクト・ステータス列内の他タスクのpositionもUPDATEでずらす。
--       担当者が設定されており、かつ期限が変更されたうえで変更後の期限が当日範囲内の場合は
--       notificationsテーブルへ'due_today_updated'通知をINSERTする（dedupe_keyでの重複はDO NOTHING）。
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
    p_position INTEGER,
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
        UPDATE tasks
           SET position = position - 1
         WHERE project_id IS NOT DISTINCT FROM v_project_id
           AND status = v_old_status
           AND position > v_old_position;

        IF p_position IS NULL THEN
            v_new_position := fn_next_task_position(v_project_id, p_status);
        ELSE
            v_new_position := p_position;
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

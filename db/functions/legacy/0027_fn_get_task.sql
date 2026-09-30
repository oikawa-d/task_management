-- 状態: 現役（根拠: alembic api/alembic/versions/0028_align_task_api_contracts.py の downgrade() で
--       DB_DIR / "functions/legacy" / f"0027_{filename}" として動的に参照される
--       （filenameに"fn_get_task.sql"を含むループ）。
--       同名の現役オブジェクトが db/functions/fn_get_task.sql に存在する）
-- 概要: タスクIDを指定して単一タスクとそのプロジェクトの有効状態を取得する。契約統一前の版。
-- 引数: p_task_id UUID — 取得対象のタスクID
-- 戻り値: TABLE(task tasks, project_is_active BOOLEAN) — 該当タスク本体と、
--       そのプロジェクトの有効状態
-- 副作用: なし
CREATE OR REPLACE FUNCTION fn_get_task(p_task_id UUID)
RETURNS TABLE (task tasks, project_is_active BOOLEAN)
LANGUAGE sql STABLE AS $$
    SELECT t, p.is_active FROM tasks t LEFT JOIN projects p ON p.id = t.project_id WHERE t.id = p_task_id;
$$;

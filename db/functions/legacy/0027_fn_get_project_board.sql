-- 状態: 現役（根拠: alembic api/alembic/versions/0028_align_task_api_contracts.py の downgrade() で
--       DB_DIR / "functions/legacy" / f"0027_{filename}" として動的に参照される
--       （filenameに"fn_get_project_board.sql"を含むループ）。
--       同名の現役オブジェクトが db/functions/fn_get_project_board.sql に存在する）
-- 概要: プロジェクトのカンバンボード表示用にタスク一覧を取得する。契約統一前の版。
-- 引数: p_project_id UUID — 対象プロジェクトID
--       p_include_inactive BOOLEAN — 無効化済みタスクを含めるか
-- 戻り値: TABLE(task tasks, project_is_active BOOLEAN) — 条件に合致するタスク本体と、
--       そのプロジェクトの有効状態
-- 副作用: なし
CREATE OR REPLACE FUNCTION fn_get_project_board(p_project_id UUID, p_include_inactive BOOLEAN)
RETURNS TABLE (task tasks, project_is_active BOOLEAN)
LANGUAGE sql STABLE AS $$
    SELECT t, p.is_active FROM tasks t LEFT JOIN projects p ON p.id = t.project_id
    WHERE t.project_id = p_project_id AND (p_include_inactive OR t.is_active = true)
    ORDER BY t.status, t.position;
$$;

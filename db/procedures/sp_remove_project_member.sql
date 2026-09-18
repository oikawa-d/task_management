-- 概要: プロジェクトメンバーを削除する。オーナーは削除できない。削除対象がプロジェクト内タスクの担当者になっている場合は担当を解除する。
-- 引数: p_project_id UUID — 対象プロジェクトID / p_user_id UUID — 削除対象ユーザーID
-- 戻り値: なし
-- 副作用: tasksテーブルの該当プロジェクト・担当者に一致する行のassignee_idをNULLにUPDATE。project_membersテーブルから対象行をDELETE。対象ユーザーがプロジェクトオーナーの場合はERRCODE 'P0004'でRAISE EXCEPTIONする。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_remove_project_member(
    p_project_id UUID,
    p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM projects WHERE id = p_project_id AND owner_id = p_user_id
    ) THEN
        RAISE EXCEPTION 'owner cannot be removed from project' USING ERRCODE = 'P0004';
    END IF;

    UPDATE tasks SET assignee_id = NULL WHERE project_id = p_project_id AND assignee_id = p_user_id;

    DELETE FROM project_members WHERE project_id = p_project_id AND user_id = p_user_id;
END;
$$;

-- 概要: 指定ユーザーをプロジェクトメンバーとして追加する。既にメンバーの場合は例外を送出する。
-- 引数: p_project_id UUID — 追加先プロジェクトID / p_user_id UUID — 追加対象ユーザーID / p_invited_by UUID — 招待した人のユーザーID
-- 戻り値: なし
-- 副作用: project_membersテーブルへINSERT。既に登録済みの場合はRAISE EXCEPTION（ERRCODE 'P0003'）で呼び出し元トランザクションをエラーにする。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_add_project_member(
    p_project_id UUID,
    p_user_id UUID,
    p_invited_by UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM project_members WHERE project_id = p_project_id AND user_id = p_user_id
    ) THEN
        RAISE EXCEPTION 'user is already a project member' USING ERRCODE = 'P0003';
    END IF;

    INSERT INTO project_members (project_id, user_id, invited_by)
    VALUES (p_project_id, p_user_id, p_invited_by);
END;
$$;

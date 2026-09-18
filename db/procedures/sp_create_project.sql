-- 概要: 新規プロジェクトを作成し、オーナーを最初のメンバーとして登録する。
-- 引数: p_owner_id UUID — オーナーとなるユーザーID / p_name VARCHAR — プロジェクト名 / p_description TEXT — 説明 / p_start_at TIMESTAMPTZ — 開始日時 / p_end_at TIMESTAMPTZ — 終了日時
-- 戻り値: p_project_id UUID — 作成されたプロジェクトのID
-- 副作用: projectsテーブルへINSERTし、project_membersテーブルへオーナーを招待者NULLでINSERT。p_end_atがp_start_atより前の場合はERRCODE 'P0009'でRAISE EXCEPTIONする。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_create_project(
    p_owner_id UUID,
    p_name VARCHAR,
    p_description TEXT,
    p_start_at TIMESTAMPTZ,
    p_end_at TIMESTAMPTZ,
    OUT p_project_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_start_at IS NOT NULL AND p_end_at IS NOT NULL AND p_end_at < p_start_at THEN
        RAISE EXCEPTION 'end_at must not be before start_at' USING ERRCODE = 'P0009';
    END IF;

    INSERT INTO projects (owner_id, name, description, start_at, end_at)
    VALUES (p_owner_id, p_name, p_description, p_start_at, p_end_at)
    RETURNING id INTO p_project_id;

    INSERT INTO project_members (project_id, user_id, invited_by)
    VALUES (p_project_id, p_owner_id, NULL);
END;
$$;

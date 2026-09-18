-- 概要: プロジェクトの基本情報（名称・説明・期間）を更新する。
-- 引数: p_project_id UUID — 対象プロジェクトID / p_name VARCHAR — プロジェクト名 / p_description TEXT — 説明 / p_start_at TIMESTAMPTZ — 開始日時 / p_end_at TIMESTAMPTZ — 終了日時
-- 戻り値: なし
-- 副作用: projectsテーブルをUPDATE。p_end_atがp_start_atより前の場合はERRCODE 'P0009'でRAISE EXCEPTIONする。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_update_project(
    p_project_id UUID,
    p_name VARCHAR,
    p_description TEXT,
    p_start_at TIMESTAMPTZ,
    p_end_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_start_at IS NOT NULL AND p_end_at IS NOT NULL AND p_end_at < p_start_at THEN
        RAISE EXCEPTION 'end_at must not be before start_at' USING ERRCODE = 'P0009';
    END IF;

    UPDATE projects
       SET name = p_name,
           description = p_description,
           start_at = p_start_at,
           end_at = p_end_at
     WHERE id = p_project_id;
END;
$$;

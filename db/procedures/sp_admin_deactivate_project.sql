-- 概要: 管理者操作としてプロジェクトの有効/無効状態を切り替える。
-- 引数: p_project_id UUID — 対象プロジェクトID / p_is_active BOOLEAN — 設定する有効状態
-- 戻り値: なし
-- 副作用: projectsテーブルのis_activeをUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_admin_deactivate_project(
    p_project_id UUID,
    p_is_active BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE projects SET is_active = p_is_active WHERE id = p_project_id;
END;
$$;

-- 概要: タスクの有効/無効状態を切り替える。position/statusはcompactionを行わずそのまま維持する。
-- 引数: p_task_id UUID — 対象タスクID / p_is_active BOOLEAN — 設定する有効状態
-- 戻り値: なし
-- 副作用: tasksテーブルのis_activeとversion（+1）をUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_deactivate_task(
    p_task_id UUID,
    p_is_active BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- position/status は変更しない（compaction を行わない）。
    UPDATE tasks
       SET is_active = p_is_active,
           version = version + 1
     WHERE id = p_task_id;
END;
$$;

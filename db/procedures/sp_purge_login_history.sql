-- 概要: 保持期間を超えたログイン履歴を削除する（バッチ用）。
-- 引数: p_retention_days INTEGER — 保持日数
-- 戻り値: なし
-- 副作用: login_historyテーブルから保持期間超過分をDELETE。他のpurge系SPと異なりp_retention_daysの正数チェックは行わない。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_purge_login_history(
    p_retention_days INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM login_history
    WHERE created_at < now() - (p_retention_days || ' days')::interval;
END;
$$;

-- 概要: 保持期間を超えたAPI呼び出し履歴を削除する（バッチ用）。
-- 引数: p_retention_days INTEGER — 保持日数（0以下は不可）
-- 戻り値: なし
-- 副作用: api_historyテーブルから保持期間超過分をDELETE。p_retention_daysが0以下の場合はRAISE EXCEPTIONする。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_purge_api_history(p_retention_days INTEGER)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_retention_days <= 0 THEN
        RAISE EXCEPTION 'p_retention_days must be positive';
    END IF;
    DELETE FROM api_history
     WHERE created_at < now() - (p_retention_days || ' days')::interval;
END;
$$;

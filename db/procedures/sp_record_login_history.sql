-- 概要: ログイン試行の履歴を1件記録する。成功・失敗いずれの試行も記録対象とする。
-- 引数: p_user_id UUID — ログイン試行のユーザーID（不明な場合はNULL可） / p_login_identifier VARCHAR — 入力されたログイン識別子（ユーザー名やメールアドレス） / p_login_method VARCHAR — ログイン方式 / p_ip_address INET — 接続元IPアドレス / p_user_agent TEXT — User-Agent文字列 / p_success BOOLEAN — 成否 / p_failure_reason VARCHAR — 失敗理由（成功時はNULL）
-- 戻り値: なし
-- 副作用: login_historyテーブルへINSERT。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_record_login_history(
    p_user_id UUID,
    p_login_identifier VARCHAR,
    p_login_method VARCHAR,
    p_ip_address INET,
    p_user_agent TEXT,
    p_success BOOLEAN,
    p_failure_reason VARCHAR
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO login_history (
        user_id, login_identifier, login_method, ip_address, user_agent, success, failure_reason
    ) VALUES (
        p_user_id, p_login_identifier, p_login_method, p_ip_address, p_user_agent, p_success, p_failure_reason
    );
END;
$$;

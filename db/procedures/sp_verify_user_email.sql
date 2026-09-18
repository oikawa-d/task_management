-- 概要: ユーザーのメールアドレスを確認済みにする。
-- 引数: p_user_id UUID — 対象ユーザーID
-- 戻り値: なし
-- 副作用: usersテーブルのemail_verified_atを現在時刻でUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_verify_user_email(
    p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE users SET email_verified_at = now() WHERE id = p_user_id;
END;
$$;

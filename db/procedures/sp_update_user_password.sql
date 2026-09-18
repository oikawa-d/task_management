-- 概要: ユーザーのパスワードハッシュを更新する。
-- 引数: p_user_id UUID — 対象ユーザーID / p_password_hash TEXT — 更新後のハッシュ化済みパスワード
-- 戻り値: なし
-- 副作用: usersテーブルのpassword_hashをUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_update_user_password(
    p_user_id UUID,
    p_password_hash TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE users SET password_hash = p_password_hash WHERE id = p_user_id;
END;
$$;

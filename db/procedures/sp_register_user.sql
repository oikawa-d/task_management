-- 概要: 新規ユーザーを登録する。username/emailは大文字小文字を区別せず重複チェックする。
-- 引数: p_username VARCHAR — ユーザー名 / p_email VARCHAR — メールアドレス / p_password_hash TEXT — ハッシュ化済みパスワード
-- 戻り値: p_user_id UUID — 作成されたユーザーのID
-- 副作用: usersテーブルへINSERT。username重複時はERRCODE 'P0001'、email重複時は'P0002'でRAISE EXCEPTIONする。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_register_user(
    p_username VARCHAR,
    p_email VARCHAR,
    p_password_hash TEXT,
    OUT p_user_id UUID
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE lower(username) = lower(p_username)) THEN
        RAISE EXCEPTION 'username already exists' USING ERRCODE = 'P0001';
    END IF;

    IF EXISTS (SELECT 1 FROM users WHERE lower(email) = lower(p_email)) THEN
        RAISE EXCEPTION 'email already exists' USING ERRCODE = 'P0002';
    END IF;

    INSERT INTO users (username, email, password_hash)
    VALUES (p_username, p_email, p_password_hash)
    RETURNING id INTO p_user_id;
END;
$$;

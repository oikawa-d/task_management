-- 概要: ユーザー名またはメールアドレス（大文字小文字を区別しない）のいずれかに一致するユーザーを検索する（ログイン識別子解決用）
-- 引数: p_identifier VARCHAR — ユーザー名またはメールアドレス
-- 戻り値: SETOF users — 合致するユーザー行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/user_repository.py
CREATE OR REPLACE FUNCTION fn_find_user_by_identifier(
    p_identifier VARCHAR
) RETURNS SETOF users
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM users
    WHERE lower(username) = lower(p_identifier)
       OR lower(email) = lower(p_identifier);
$$;

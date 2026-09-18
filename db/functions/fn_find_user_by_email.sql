-- 概要: メールアドレス（大文字小文字を区別しない）でユーザーを検索する
-- 引数: p_email VARCHAR — 検索対象のメールアドレス
-- 戻り値: SETOF users — 合致するユーザー行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/user_repository.py
CREATE OR REPLACE FUNCTION fn_find_user_by_email(
    p_email VARCHAR
) RETURNS SETOF users
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM users WHERE lower(email) = lower(p_email);
$$;

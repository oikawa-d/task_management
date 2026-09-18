-- 概要: IDを指定してユーザー1件を取得する
-- 引数: p_user_id UUID — 取得対象のユーザーID
-- 戻り値: SETOF users — 合致するユーザー行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/user_repository.py
CREATE OR REPLACE FUNCTION fn_get_user(
    p_user_id UUID
) RETURNS SETOF users
LANGUAGE sql
STABLE
AS $$
    SELECT * FROM users WHERE id = p_user_id;
$$;

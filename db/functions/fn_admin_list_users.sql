-- 概要: 管理者向けにユーザー一覧を検索条件・ページングで絞り込み、全件数を付与して返す
-- 引数: p_query VARCHAR — ユーザー名/メールアドレスの部分一致検索語（NULLで無視）／p_role VARCHAR — ロールで絞り込み（NULLで無視）／p_is_active BOOLEAN — 有効/無効で絞り込み（NULLで無視）／p_limit INTEGER — 取得件数上限／p_offset INTEGER — 取得開始位置
-- 戻り値: TABLE("user" users, total_count BIGINT) — 条件に合致したユーザー行と、絞り込み後の全件数
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/admin_repository.py
CREATE OR REPLACE FUNCTION fn_admin_list_users(
    p_query VARCHAR,
    p_role VARCHAR,
    p_is_active BOOLEAN,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    "user" users,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT u.id, count(*) OVER () AS total_count
        FROM users u
        WHERE (p_query IS NULL OR lower(u.username) LIKE '%' || lower(p_query) || '%'
                               OR lower(u.email) LIKE '%' || lower(p_query) || '%')
          AND (p_role IS NULL OR u.role = p_role)
          AND (p_is_active IS NULL OR u.is_active = p_is_active)
        ORDER BY u.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT u AS "user", s.total_count
    FROM scoped s
    JOIN users u ON u.id = s.id
    ORDER BY u.created_at DESC;
$$;

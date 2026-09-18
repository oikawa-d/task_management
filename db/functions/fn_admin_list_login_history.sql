-- 概要: 管理者向けにログイン履歴を検索条件・ページングで絞り込み、対象ユーザー情報と全件数を付与して返す
-- 引数: p_user_id UUID — 対象ユーザーで絞り込み（NULLで全ユーザー）／p_query VARCHAR — ログイン識別子の部分一致検索語（NULLで無視）／p_login_method VARCHAR — ログイン方式で絞り込み（NULLで無視）／p_success BOOLEAN — 成功可否で絞り込み（NULLで無視）／p_from TIMESTAMPTZ — 検索期間の開始（NULLで無視）／p_to TIMESTAMPTZ — 検索期間の終了（NULLで無視）／p_limit INTEGER — 取得件数上限／p_offset INTEGER — 取得開始位置
-- 戻り値: TABLE(history login_history, "user" users, total_count BIGINT) — 条件に合致したログイン履歴行と紐づくユーザー、絞り込み後の全件数
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/admin_repository.py
CREATE OR REPLACE FUNCTION fn_admin_list_login_history(
    p_user_id UUID,
    p_query VARCHAR,
    p_login_method VARCHAR,
    p_success BOOLEAN,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS TABLE (
    history login_history,
    "user" users,
    total_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT h.id, count(*) OVER () AS total_count
        FROM login_history h
        WHERE (p_user_id IS NULL OR h.user_id = p_user_id)
          AND (p_query IS NULL OR lower(h.login_identifier) LIKE '%' || lower(p_query) || '%')
          AND (p_login_method IS NULL OR h.login_method = p_login_method)
          AND (p_success IS NULL OR h.success = p_success)
          AND (p_from IS NULL OR h.created_at >= p_from)
          AND (p_to IS NULL OR h.created_at < p_to)
        ORDER BY h.created_at DESC
        LIMIT p_limit OFFSET p_offset
    )
    SELECT h AS history, u AS "user", s.total_count
    FROM scoped s
    JOIN login_history h ON h.id = s.id
    LEFT JOIN users u ON u.id = h.user_id
    ORDER BY h.created_at DESC;
$$;

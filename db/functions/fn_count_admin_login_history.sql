-- 概要: 管理者向けログイン履歴一覧と同じ検索条件に合致する件数のみを算出する（ページング用の総件数取得）
-- 引数: p_user_id UUID — 対象ユーザーで絞り込み（NULLで全ユーザー）／p_query VARCHAR — ログイン識別子の部分一致検索語（NULLで無視）／p_login_method VARCHAR — ログイン方式で絞り込み（NULLで無視）／p_success BOOLEAN — 成功可否で絞り込み（NULLで無視）／p_from TIMESTAMPTZ — 検索期間の開始（NULLで無視）／p_to TIMESTAMPTZ — 検索期間の終了（NULLで無視）
-- 戻り値: BIGINT — 条件に合致するログイン履歴の件数
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/admin_repository.py
CREATE OR REPLACE FUNCTION fn_count_admin_login_history(
    p_user_id UUID,
    p_query VARCHAR,
    p_login_method VARCHAR,
    p_success BOOLEAN,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM login_history h
    WHERE (p_user_id IS NULL OR h.user_id = p_user_id)
      AND (p_query IS NULL OR lower(h.login_identifier) LIKE '%' || lower(p_query) || '%')
      AND (p_login_method IS NULL OR h.login_method = p_login_method)
      AND (p_success IS NULL OR h.success = p_success)
      AND (p_from IS NULL OR h.created_at >= p_from)
      AND (p_to IS NULL OR h.created_at < p_to);
$$;

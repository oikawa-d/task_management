-- 概要: プロジェクトへの招待候補として、まだメンバーでない有効ユーザーをユーザー名/氏名の前方一致検索とページングで取得する
-- 引数: p_project_id UUID — 対象プロジェクトID（既存メンバーの除外に使用）／p_query VARCHAR — ユーザー名または氏名の前方一致検索語（NULLまたは空文字で無視）／p_limit INTEGER — 取得件数上限／p_offset INTEGER — 取得開始位置
-- 戻り値: SETOF users — ユーザー名昇順の候補ユーザー行（存在しない場合は空集合）
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/project_member_repository.py
CREATE OR REPLACE FUNCTION fn_search_member_candidates(
    p_project_id UUID,
    p_query VARCHAR,
    p_limit INTEGER,
    p_offset INTEGER
) RETURNS SETOF users
LANGUAGE sql
STABLE
AS $$
    SELECT u.*
    FROM users u
    WHERE u.is_active = true
      AND NOT EXISTS (
          SELECT 1 FROM project_members pm
          WHERE pm.project_id = p_project_id AND pm.user_id = u.id
      )
      AND (
          p_query IS NULL
          OR p_query = ''
          OR u.username ILIKE p_query || '%'
          OR concat_ws(' ', u.last_name, u.first_name) ILIKE p_query || '%'
      )
    ORDER BY u.username
    LIMIT p_limit OFFSET p_offset;
$$;

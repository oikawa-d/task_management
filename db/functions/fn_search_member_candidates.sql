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
      AND (p_query IS NULL OR p_query = '' OR u.username ILIKE p_query || '%')
    ORDER BY u.username
    LIMIT p_limit OFFSET p_offset;
$$;

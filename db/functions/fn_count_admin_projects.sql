CREATE OR REPLACE FUNCTION fn_count_admin_projects(
    p_query VARCHAR,
    p_is_active BOOLEAN
) RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)
    FROM projects p
    WHERE (p_query IS NULL OR lower(p.name) LIKE '%' || lower(p_query) || '%')
      AND (p_is_active IS NULL OR p.is_active = p_is_active);
$$;

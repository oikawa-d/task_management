CREATE OR REPLACE PROCEDURE sp_purge_notifications(
    p_retention_days INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_retention_days <= 0 THEN
        RAISE EXCEPTION 'p_retention_days must be positive';
    END IF;
    DELETE FROM notifications
     WHERE created_at < now() - (p_retention_days || ' days')::interval;
END;
$$;

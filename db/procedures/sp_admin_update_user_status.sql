CREATE OR REPLACE PROCEDURE sp_admin_update_user_status(
    p_actor_id UUID,
    p_target_id UUID,
    p_is_active BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_role VARCHAR;
    v_current_is_active BOOLEAN;
    v_other_active_admins BIGINT;
BEGIN
    IF p_actor_id = p_target_id THEN
        RAISE EXCEPTION 'self modification is not allowed' USING ERRCODE = 'P0007';
    END IF;

    -- 対象ユーザー単位で直列化し、並行するrole/status変更と最後のadmin判定が競合しないようにする
    PERFORM pg_advisory_xact_lock(hashtextextended(p_target_id::text, 0));

    SELECT role, is_active INTO v_current_role, v_current_is_active
    FROM users WHERE id = p_target_id;

    IF v_current_role = 'admin' AND v_current_is_active = true AND p_is_active = false THEN
        SELECT count(*) INTO v_other_active_admins
        FROM users WHERE role = 'admin' AND is_active = true AND id <> p_target_id;

        IF v_other_active_admins = 0 THEN
            RAISE EXCEPTION 'last active admin cannot be deactivated' USING ERRCODE = 'P0008';
        END IF;
    END IF;

    UPDATE users SET is_active = p_is_active WHERE id = p_target_id;
END;
$$;

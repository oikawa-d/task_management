CREATE OR REPLACE PROCEDURE sp_admin_update_user_role(
    p_actor_id UUID,
    p_target_id UUID,
    p_new_role VARCHAR
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

    -- 「有効adminが最低1人残る」はusersテーブル全体に対するグローバルな不変条件のため、
    -- 対象ユーザー単位のロックでは異なる2人のadminへの同時降格を直列化できない。
    -- admin保護判定専用の固定キーでrole/status変更全体を直列化する。
    PERFORM pg_advisory_xact_lock(hashtext('admin_protection'));

    SELECT role, is_active INTO v_current_role, v_current_is_active
    FROM users WHERE id = p_target_id;

    IF v_current_role = 'admin' AND v_current_is_active = true AND p_new_role <> 'admin' THEN
        SELECT count(*) INTO v_other_active_admins
        FROM users WHERE role = 'admin' AND is_active = true AND id <> p_target_id;

        IF v_other_active_admins = 0 THEN
            RAISE EXCEPTION 'last active admin cannot be demoted' USING ERRCODE = 'P0008';
        END IF;
    END IF;

    UPDATE users SET role = p_new_role WHERE id = p_target_id;
END;
$$;

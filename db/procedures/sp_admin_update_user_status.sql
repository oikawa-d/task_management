-- 概要: 管理者操作としてユーザーの有効/無効状態を変更する。本人への操作、および有効なadminが0人になる無効化は禁止する。
-- 引数: p_actor_id UUID — 操作を実行する管理者のユーザーID / p_target_id UUID — 状態変更対象ユーザーID / p_is_active BOOLEAN — 変更後の有効状態
-- 戻り値: p_old_is_active BOOLEAN — 変更前の有効状態
-- 副作用: usersテーブルのis_activeをUPDATE。対象行をFOR UPDATEでロックし、admin保護判定用の固定キーでpg_advisory_xact_lockによりrole/status変更全体を直列化する。自己操作時はERRCODE 'P0007'、対象ユーザー不在時は'P0010'、最後の有効adminを無効化しようとした場合は'P0008'でRAISE EXCEPTIONする。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_admin_update_user_status(
    p_actor_id UUID,
    p_target_id UUID,
    p_is_active BOOLEAN,
    OUT p_old_is_active BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_role VARCHAR;
    v_other_active_admins BIGINT;
BEGIN
    IF p_actor_id = p_target_id THEN
        RAISE EXCEPTION 'self modification is not allowed' USING ERRCODE = 'P0007';
    END IF;

    -- 「有効adminが最低1人残る」はusersテーブル全体に対するグローバルな不変条件のため、
    -- 対象ユーザー単位のロックでは異なる2人のadminへの同時降格を直列化できない。
    -- admin保護判定専用の固定キーでrole/status変更全体を直列化する。
    PERFORM pg_advisory_xact_lock(hashtext('admin_protection'));

    SELECT role, is_active INTO v_current_role, p_old_is_active
    FROM users WHERE id = p_target_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'target user not found' USING ERRCODE = 'P0010';
    END IF;

    IF v_current_role = 'admin' AND p_old_is_active = true AND p_is_active = false THEN
        SELECT count(*) INTO v_other_active_admins
        FROM users WHERE role = 'admin' AND is_active = true AND id <> p_target_id;

        IF v_other_active_admins = 0 THEN
            RAISE EXCEPTION 'last active admin cannot be deactivated' USING ERRCODE = 'P0008';
        END IF;
    END IF;

    UPDATE users SET is_active = p_is_active WHERE id = p_target_id;
END;
$$;

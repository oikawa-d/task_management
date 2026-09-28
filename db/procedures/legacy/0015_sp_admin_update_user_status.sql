-- 状態: 現役（根拠: alembic api/alembic/versions/0020_add_admin_list_total_count_and_not_found.py の
--       downgrade() から参照される。同名の現役オブジェクトが db/procedures/sp_admin_update_user_status.sql に存在する）
-- 概要: 管理者がユーザーの有効/無効を変更する。変更前の状態をOUT引数で返さず、
--       対象ユーザー不在チェックも行わない、現行版より前の版。自己変更を禁止し、
--       有効なadminが最低1人残ることをグローバルなアドバイザリロックで直列化して保証したうえで更新する。
-- 引数: p_actor_id UUID — 操作を行う管理者のユーザーID
--       p_target_id UUID — 状態変更対象のユーザーID
--       p_is_active BOOLEAN — 変更後の有効/無効
-- 戻り値: なし
-- 副作用: usersテーブルの対象行のis_activeをUPDATEする。自己変更、または最後の有効adminを
--       無効化しようとした場合は例外(P0007/P0008)を送出する。
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

    -- 「有効adminが最低1人残る」はusersテーブル全体に対するグローバルな不変条件のため、
    -- 対象ユーザー単位のロックでは異なる2人のadminへの同時降格を直列化できない。
    -- admin保護判定専用の固定キーでrole/status変更全体を直列化する。
    PERFORM pg_advisory_xact_lock(hashtext('admin_protection'));

    SELECT role, is_active INTO v_current_role, v_current_is_active
    FROM users WHERE id = p_target_id
    FOR UPDATE;

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

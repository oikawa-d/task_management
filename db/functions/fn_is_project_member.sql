-- 概要: 指定ユーザーが有効かつ、管理者またはプロジェクトメンバーとしてそのプロジェクトへのアクセス権を持つかを判定する
-- 引数: p_project_id UUID — 判定対象のプロジェクトID／p_user_id UUID — 判定対象のユーザーID
-- 戻り値: BOOLEAN — アクセス権を持つ場合はtrue
-- 副作用: なし（参照のみ）
-- 主な呼び出し元: api/app/repository/project_member_repository.py, api/app/repository/project_repository.py
CREATE OR REPLACE FUNCTION fn_is_project_member(
    p_project_id UUID,
    p_user_id UUID
) RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM users u
        WHERE u.id = p_user_id
          AND u.is_active = true
          AND (
              u.role = 'admin'
              OR EXISTS (
                  SELECT 1
                  FROM project_members pm
                  WHERE pm.project_id = p_project_id
                    AND pm.user_id = p_user_id
              )
          )
    );
$$;

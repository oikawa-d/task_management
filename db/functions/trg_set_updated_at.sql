-- 概要: BEFORE UPDATEトリガーとして呼び出され、更新対象行のupdated_atを現在時刻に自動更新する
-- 引数: なし（トリガー関数のためNEW/OLDの暗黙引数を使用）
-- 戻り値: TRIGGER — updated_atを更新したNEW行
-- 副作用: なし（呼び出し元のUPDATE対象行のupdated_at列を書き換えるのみで、追加のテーブル操作は行わない）
-- 主な呼び出し元: users/projects/tasks/task_comments/batch_history 等のBEFORE UPDATEトリガー（api/alembic/versions/0005・0010・0014）
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

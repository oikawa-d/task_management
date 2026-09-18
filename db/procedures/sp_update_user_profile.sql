-- 概要: ユーザーのプロフィール情報（氏名・かな・生年月日）を更新する。
-- 引数: p_user_id UUID — 対象ユーザーID / p_last_name VARCHAR — 姓 / p_first_name VARCHAR — 名 / p_last_name_kana VARCHAR — 姓（かな） / p_first_name_kana VARCHAR — 名（かな） / p_birth_date DATE — 生年月日
-- 戻り値: なし
-- 副作用: usersテーブルをUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_update_user_profile(
    p_user_id UUID,
    p_last_name VARCHAR,
    p_first_name VARCHAR,
    p_last_name_kana VARCHAR,
    p_first_name_kana VARCHAR,
    p_birth_date DATE
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE users
       SET last_name = p_last_name,
           first_name = p_first_name,
           last_name_kana = p_last_name_kana,
           first_name_kana = p_first_name_kana,
           birth_date = p_birth_date
     WHERE id = p_user_id;
END;
$$;

-- 概要: OAuthアカウント連携情報を登録する。既に同一provider/provider_user_idの連携が存在する場合は何もしない。連携時にユーザーのメール確認日時が未設定なら設定する。
-- 引数: p_user_id UUID — 連携先ユーザーID / p_provider VARCHAR — OAuthプロバイダ名 / p_provider_user_id TEXT — プロバイダ側のユーザーID
-- 戻り値: なし
-- 副作用: oauth_accountsテーブルへINSERT（重複時はON CONFLICT DO NOTHING）。usersテーブルのemail_verified_atが未設定の場合のみ現在時刻でUPDATE。COMMIT/ROLLBACKは本プロシージャ内では行わない。
CREATE OR REPLACE PROCEDURE sp_upsert_oauth_account(
    p_user_id UUID,
    p_provider VARCHAR,
    p_provider_user_id TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO oauth_accounts (user_id, provider, provider_user_id)
    VALUES (p_user_id, p_provider, p_provider_user_id)
    ON CONFLICT (provider, provider_user_id) DO NOTHING;

    UPDATE users
       SET email_verified_at = COALESCE(email_verified_at, now())
     WHERE id = p_user_id;
END;
$$;

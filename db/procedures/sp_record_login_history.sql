CREATE OR REPLACE PROCEDURE sp_record_login_history(
    p_user_id UUID,
    p_login_identifier VARCHAR,
    p_login_method VARCHAR,
    p_ip_address INET,
    p_user_agent TEXT,
    p_success BOOLEAN,
    p_failure_reason VARCHAR
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO login_history (
        user_id, login_identifier, login_method, ip_address, user_agent, success, failure_reason
    ) VALUES (
        p_user_id, p_login_identifier, p_login_method, p_ip_address, p_user_agent, p_success, p_failure_reason
    );
END;
$$;

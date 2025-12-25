-- CRM onboarding helper
-- Стартует (или возвращает существующую) сессию онбординга по account_id.
-- Учитывает ограничение: один active (pending/running) онбординг на аккаунт.

CREATE SCHEMA IF NOT EXISTS crm;

CREATE OR REPLACE FUNCTION crm.fn_start_onboarding_session(
    p_account_id bigint,
    p_status     text  DEFAULT 'pending',
    p_steps      jsonb DEFAULT NULL
)
RETURNS TABLE (
    onboarding_id     bigint,
    onboarding_status text
)
LANGUAGE plpgsql
AS
$$
DECLARE
    v_id     bigint;
    v_status text;
    v_steps  jsonb;
BEGIN
    IF p_account_id IS NULL THEN
        RAISE EXCEPTION 'p_account_id must not be null';
    END IF;

    -- Проверяем, что аккаунт существует
    PERFORM 1
      FROM crm.accounts a
     WHERE a.id = p_account_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Account % not found in crm.accounts', p_account_id;
    END IF;

    -- Пытаемся переиспользовать уже активный (pending/running) онбординг
    SELECT s.id, s.status
      INTO v_id, v_status
      FROM crm.onboarding_sessions s
     WHERE s.account_id = p_account_id
       AND s.status IN ('pending', 'running')
     ORDER BY s.created_at DESC
     LIMIT 1;

    IF v_id IS NOT NULL THEN
        onboarding_id     := v_id;
        onboarding_status := v_status;
        RETURN NEXT;
        RETURN;
    END IF;

    -- Если шаги не заданы извне — берём дефолтный шаблон
    IF p_steps IS NULL THEN
        v_steps := jsonb_build_array(
            jsonb_build_object('step_code','contract',     'status','pending'),
            jsonb_build_object('step_code','integration',  'status','pending'),
            jsonb_build_object('step_code','data_import',  'status','pending'),
            jsonb_build_object('step_code','pilot_run',    'status','pending'),
            jsonb_build_object('step_code','training',     'status','pending'),
            jsonb_build_object('step_code','go_live',      'status','pending')
        );
    ELSE
        v_steps := p_steps;
    END IF;

    INSERT INTO crm.onboarding_sessions (account_id, status, steps, summary)
    VALUES (
        p_account_id,
        COALESCE(p_status, 'pending'),
        v_steps,
        '{}'::jsonb
    )
    RETURNING id, status
      INTO v_id, v_status;

    onboarding_id     := v_id;
    onboarding_status := v_status;
    RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION crm.fn_start_onboarding_session(bigint, text, jsonb) IS
    'Стартует (или возвращает существующую) сессию онбординга по account_id (pending/running).';

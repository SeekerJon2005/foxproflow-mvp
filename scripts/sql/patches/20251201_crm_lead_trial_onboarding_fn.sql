-- scripts/sql/patches/20251201_crm_lead_trial_onboarding_fn.sql
-- Оркестратор: lead → win → tenant → trial subscription → onboarding_session
-- Использует:
--  - crm.leads
--  - crm.fn_start_trial_subscription(...)
--  - crm.fn_start_onboarding_session(...)
--
-- NDC: только CREATE SCHEMA IF NOT EXISTS и CREATE OR REPLACE FUNCTION.
--      Никаких DROP / разрушающих ALTER.

CREATE SCHEMA IF NOT EXISTS crm;

CREATE OR REPLACE FUNCTION crm.fn_lead_win_trial_and_onboarding(
    p_lead_id        bigint,
    p_product_code   text          DEFAULT 'logistics',
    p_plan_code      text          DEFAULT 'mvp-5-15-trucks',
    p_currency       text          DEFAULT 'RUB',
    p_amount_month   numeric(14,2) DEFAULT 0,
    p_billing_period text          DEFAULT 'monthly',
    p_trial_days     integer       DEFAULT 30
)
RETURNS TABLE (
    lead_id_out        bigint,
    tenant_id_out      uuid,
    account_id_out     bigint,
    subscription_id    bigint,
    subscription_v2_id uuid,
    onboarding_id      bigint
)
LANGUAGE plpgsql
AS
$$
DECLARE
    v_lead          crm.leads%ROWTYPE;
    v_tenant_id     uuid;
    v_account_id    bigint;
    v_sub_id        bigint;
    v_sub_v2_id     uuid;
    v_onboarding_id bigint;

    v_trial_rec     record;
    v_onb_rec       record;
BEGIN
    --------------------------------------------------------------------
    -- 1. Забираем лид и блокируем строку (на случай гонок)
    --------------------------------------------------------------------
    SELECT *
      INTO v_lead
      FROM crm.leads l
     WHERE l.id = p_lead_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Lead % not found in crm.leads', p_lead_id;
    END IF;

    --------------------------------------------------------------------
    -- 2. Получаем tenant_id из payload или создаём новый.
    --    При создании/исправлении пишем его обратно в payload лида.
    --------------------------------------------------------------------
    IF v_lead.payload ? 'tenant_id' THEN
        BEGIN
            v_tenant_id := (v_lead.payload->>'tenant_id')::uuid;
        EXCEPTION WHEN others THEN
            -- В payload лежит мусор — генерим новый tenant_id и сразу чиним данные.
            v_tenant_id := gen_random_uuid();

            UPDATE crm.leads
               SET payload   = jsonb_set(
                                   COALESCE(payload, '{}'::jsonb),
                                   '{tenant_id}',
                                   to_jsonb(v_tenant_id::text),
                                   true
                               ),
                   updated_at = now()
             WHERE id = v_lead.id;
        END;
    ELSE
        v_tenant_id := gen_random_uuid();

        UPDATE crm.leads
           SET payload   = jsonb_set(
                               COALESCE(payload, '{}'::jsonb),
                               '{tenant_id}',
                               to_jsonb(v_tenant_id::text),
                               true
                           ),
               updated_at = now()
         WHERE id = v_lead.id;
    END IF;

    --------------------------------------------------------------------
    -- 3. Помечаем лид как won (idempotent)
    --------------------------------------------------------------------
    IF v_lead.status IS DISTINCT FROM 'won' THEN
        UPDATE crm.leads
           SET status     = 'won',
               updated_at = now()
         WHERE id = v_lead.id;
    END IF;

    --------------------------------------------------------------------
    -- 4. Стартуем trial-подписку через crm.fn_start_trial_subscription(...)
    --    Эта функция:
    --      - создаёт/обновляет crm.accounts по tenant_id,
    --      - создаёт/обновляет crm.subscriptions (v1),
    --      - создаёт/обновляет crm.subscription (v2).
    --    Результат забираем в RECORD, чтобы не зависеть от имён колонок.
    --------------------------------------------------------------------
    SELECT *
      INTO v_trial_rec
      FROM crm.fn_start_trial_subscription(
               v_tenant_id,
               v_lead.company_name,
               v_lead.country,
               v_lead.region,
               p_product_code,
               p_plan_code,
               p_currency,
               p_amount_month,
               p_billing_period,
               p_trial_days
           );

    v_account_id    := v_trial_rec.account_id;
    v_sub_id        := v_trial_rec.subscription_id;
    v_sub_v2_id     := v_trial_rec.subscription_v2_id;

    --------------------------------------------------------------------
    -- 5. Стартуем онбординг по этому аккаунту
    --------------------------------------------------------------------
    SELECT *
      INTO v_onb_rec
      FROM crm.fn_start_onboarding_session(v_account_id);

    v_onboarding_id := v_onb_rec.onboarding_id;

    --------------------------------------------------------------------
    -- 6. Заполняем OUT-поля и отдаём одну строку наружу
    --------------------------------------------------------------------
    lead_id_out        := v_lead.id;
    tenant_id_out      := v_tenant_id;
    account_id_out     := v_account_id;
    subscription_id    := v_sub_id;
    subscription_v2_id := v_sub_v2_id;
    onboarding_id      := v_onboarding_id;

    RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION crm.fn_lead_win_trial_and_onboarding(
    bigint, text, text, text, numeric, text, integer
) IS
    'Оркестратор CRM: лид → won → trial-подписка (v1+v2) → сессия онбординга.';

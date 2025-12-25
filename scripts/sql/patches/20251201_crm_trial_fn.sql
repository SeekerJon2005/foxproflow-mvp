-- CRM trial bootstrap function
-- Задача:
--  - обеспечить, что для tenant_id есть account (crm.accounts);
--  - обеспечить, что есть продукт (crm.products);
--  - создать/обновить trial-подписку v1 (crm.subscriptions);
--  - создать/обновить trial-подписку v2 (crm.subscription);
--  - crm.tenant зеркалирует основной tenant_id (1:1 по UUID).

CREATE SCHEMA IF NOT EXISTS crm;

CREATE OR REPLACE FUNCTION crm.fn_start_trial_subscription(
    p_tenant_id      uuid,
    p_company_name   text,
    p_country        text DEFAULT NULL,
    p_region         text DEFAULT NULL,
    p_product_code   text DEFAULT 'logistics',              -- код продукта в crm.products
    p_plan_code      text DEFAULT 'mvp-5-15-trucks',        -- код тарифа/плана
    p_currency       text DEFAULT 'RUB',
    p_amount_month   numeric(14,2) DEFAULT 0,               -- стоимость в месяц
    p_billing_period text DEFAULT 'monthly',                -- monthly/yearly
    p_trial_days     integer DEFAULT 30                     -- длительность trial
)
RETURNS TABLE (
    account_id          bigint,
    subscription_id     bigint,
    subscription_v2_id  uuid
)
LANGUAGE plpgsql
AS
$$
DECLARE
    v_account_id             bigint;
    v_subscription_id        bigint;
    v_subscription_status    text;
    v_subscription_v2_id     uuid;
    v_now                    timestamptz := now();
    v_trial_ends_at          timestamptz;
BEGIN
    IF p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'p_tenant_id must not be null';
    END IF;

    v_trial_ends_at := v_now + (p_trial_days || ' days')::interval;

    ------------------------------------------------------------------------
    -- 1. Upsert продукта в crm.products (минимальный stub, если нет)
    ------------------------------------------------------------------------
    PERFORM 1
      FROM crm.products p
     WHERE p.code = p_product_code;

    IF NOT FOUND THEN
        INSERT INTO crm.products (code, name, description, payload)
        VALUES (p_product_code, p_product_code, NULL, '{}'::jsonb);
    END IF;

    ------------------------------------------------------------------------
    -- 2. Upsert аккаунта в crm.accounts по tenant_id
    ------------------------------------------------------------------------
    SELECT a.id
      INTO v_account_id
      FROM crm.accounts a
     WHERE a.tenant_id = p_tenant_id;

    IF v_account_id IS NULL THEN
        INSERT INTO crm.accounts (tenant_id, company_name, country, region, payload)
        VALUES (p_tenant_id, p_company_name, p_country, p_region, '{}'::jsonb)
        RETURNING id INTO v_account_id;
    ELSE
        UPDATE crm.accounts
           SET company_name = COALESCE(p_company_name, company_name),
               country      = COALESCE(p_country,     country),
               region       = COALESCE(p_region,      region),
               updated_at   = v_now
         WHERE id = v_account_id;
    END IF;

    ------------------------------------------------------------------------
    -- 3. Upsert crm.tenant: зеркалим основной tenant_id как PK
    ------------------------------------------------------------------------
    PERFORM 1
      FROM crm.tenant t
     WHERE t.id = p_tenant_id;

    IF NOT FOUND THEN
        INSERT INTO crm.tenant (id, status, code, name, country_code, timezone, config)
        VALUES (
            p_tenant_id,
            'trial',
            NULL,
            p_company_name,
            p_country,
            NULL,
            '{}'::jsonb
        );
    ELSE
        UPDATE crm.tenant
           SET name         = COALESCE(p_company_name, name),
               country_code = COALESCE(p_country,     country_code),
               status       = COALESCE(status,        'trial'),
               updated_at   = v_now
         WHERE id = p_tenant_id;
    END IF;

    ------------------------------------------------------------------------
    -- 4. Upsert подписки v1: crm.subscriptions (по account_id + product_code)
    ------------------------------------------------------------------------
    SELECT s.id, s.status
      INTO v_subscription_id, v_subscription_status
      FROM crm.subscriptions s
     WHERE s.account_id   = v_account_id
       AND s.product_code = p_product_code
       AND s.status IN ('trial','active')
     ORDER BY s.created_at DESC
     LIMIT 1;

    IF v_subscription_id IS NULL THEN
        INSERT INTO crm.subscriptions (
            account_id, product_code, plan_code, status,
            started_at, trial_ends_at, expires_at,
            currency, amount_month, billing_period, payload
        )
        VALUES (
            v_account_id, p_product_code, p_plan_code, 'trial',
            v_now, v_trial_ends_at, NULL,
            p_currency, p_amount_month, p_billing_period, '{}'::jsonb
        )
        RETURNING id INTO v_subscription_id;
    ELSE
        -- Если уже active, не понижаем до trial
        IF v_subscription_status = 'trial' THEN
            UPDATE crm.subscriptions
               SET updated_at     = v_now,
                   status         = 'trial',
                   started_at     = COALESCE(started_at,    v_now),
                   trial_ends_at  = COALESCE(trial_ends_at, v_trial_ends_at),
                   currency       = COALESCE(currency,      p_currency),
                   amount_month   = COALESCE(amount_month,  p_amount_month),
                   billing_period = COALESCE(billing_period,p_billing_period)
             WHERE id = v_subscription_id;
        ELSE
            UPDATE crm.subscriptions
               SET updated_at     = v_now,
                   currency       = COALESCE(currency,      p_currency),
                   amount_month   = COALESCE(amount_month,  p_amount_month),
                   billing_period = COALESCE(billing_period,p_billing_period)
             WHERE id = v_subscription_id;
        END IF;
    END IF;

    ------------------------------------------------------------------------
    -- 5. Upsert подписки v2: crm.subscription (по tenant_id + plan_code)
    ------------------------------------------------------------------------
    SELECT s.id
      INTO v_subscription_v2_id
      FROM crm.subscription s
     WHERE s.tenant_id = p_tenant_id
       AND s.plan_code = p_plan_code
       AND s.status IN ('trial','active')
     ORDER BY s.created_at DESC
     LIMIT 1;

    IF v_subscription_v2_id IS NULL THEN
        INSERT INTO crm.subscription (
            tenant_id, status, plan_code, billing_period,
            currency, amount, starts_at, trial_until, ends_at, meta
        )
        VALUES (
            p_tenant_id, 'trial', p_plan_code, p_billing_period,
            p_currency, p_amount_month, v_now, v_trial_ends_at, NULL, '{}'::jsonb
        )
        RETURNING id INTO v_subscription_v2_id;
    ELSE
        UPDATE crm.subscription
           SET updated_at   = v_now,
               status       = 'trial',
               starts_at    = COALESCE(starts_at,   v_now),
               trial_until  = COALESCE(trial_until, v_trial_ends_at),
               currency     = COALESCE(currency,    p_currency),
               amount       = COALESCE(amount,      p_amount_month),
               billing_period = COALESCE(billing_period, p_billing_period)
         WHERE id = v_subscription_v2_id;
    END IF;

    account_id         := v_account_id;
    subscription_id    := v_subscription_id;
    subscription_v2_id := v_subscription_v2_id;

    RETURN NEXT;
END;
$$;

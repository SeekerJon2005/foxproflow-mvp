-- 20251206_billing_core_v1.sql
-- NDC-патч: ядро BillingFox (subscription + invoice) + базовые функции.
-- stack=sql
-- goal=Создать минимально полезное ядро биллинга и согласовать его с CRM/DevFactory.
-- summary=Создаёт billing.subscription, billing.invoice и функции fn_create_subscription_for_tenant / fn_issue_initial_invoice.

-------------------------------
-- 0. Базовая гигиена
-------------------------------

-- Расширение для gen_random_uuid(), если ещё не включено
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Гарантируем наличие схем
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'billing'
    ) THEN
        EXECUTE 'CREATE SCHEMA billing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'crm'
    ) THEN
        EXECUTE 'CREATE SCHEMA crm';
    END IF;
END
$$;

-------------------------------
-- 1. Таблица billing.subscription
-------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'billing'
          AND table_name   = 'subscription'
    ) THEN
        CREATE TABLE billing.subscription (
            subscription_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

            -- Привязка к crm.tenant.id
            tenant_id       uuid NOT NULL
                REFERENCES crm.tenant(id),

            status          text NOT NULL,        -- 'trial' | 'active' | 'suspended' | 'cancelled'
            plan_code       text NOT NULL,        -- тарифный план (например, FOXPROFLOW_DEVFACTORY_CORE)
            currency_code   text NOT NULL DEFAULT 'RUB',
            amount          numeric(18,2),        -- базовый периодический платёж (опционально)

            meta            jsonb NOT NULL DEFAULT '{}'::jsonb,

            created_at      timestamptz NOT NULL DEFAULT now(),
            created_by      text       NOT NULL,
            updated_at      timestamptz NOT NULL DEFAULT now(),
            updated_by      text       NOT NULL
        );
    END IF;
END
$$;

-------------------------------
-- 2. Таблица billing.invoice
-------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'billing'
          AND table_name   = 'invoice'
    ) THEN
        CREATE TABLE billing.invoice (
            invoice_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),

            subscription_id uuid NOT NULL
                REFERENCES billing.subscription(subscription_id),

            tenant_id       uuid NOT NULL
                REFERENCES crm.tenant(id),

            status          text NOT NULL,        -- 'issued' | 'paid' | 'cancelled'
            amount          numeric(18,2) NOT NULL,
            currency_code   text NOT NULL,
            due_date        date,                -- дата оплаты (без времени)
            issued_at       timestamptz NOT NULL DEFAULT now(),
            paid_at         timestamptz,

            meta            jsonb NOT NULL DEFAULT '{}'::jsonb,

            created_at      timestamptz NOT NULL DEFAULT now(),
            created_by      text       NOT NULL,
            updated_at      timestamptz NOT NULL DEFAULT now(),
            updated_by      text       NOT NULL
        );
    END IF;
END
$$;

-------------------------------
-- 3. Функция: создать подписку для tenant
-------------------------------

CREATE OR REPLACE FUNCTION billing.fn_create_subscription_for_tenant(
    p_tenant_id   uuid,
    p_plan_code   text,
    p_operator_id text
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_subscription_id uuid;
BEGIN
    INSERT INTO billing.subscription (
        tenant_id,
        status,
        plan_code,
        currency_code,
        amount,
        meta,
        created_by,
        updated_by
    )
    VALUES (
        p_tenant_id,
        'active',              -- базовый статус; можно расширить 'trial' при необходимости
        p_plan_code,
        'RUB',                 -- дефолт, позже можно сделать параметром
        NULL,                  -- базовую сумму можно проставлять позже или из отдельной таблицы тарифов
        '{}'::jsonb,
        p_operator_id,
        p_operator_id
    )
    RETURNING subscription_id INTO v_subscription_id;

    RETURN v_subscription_id;
END;
$$;

-------------------------------
-- 4. Функция: выписать первичный счёт по подписке
-------------------------------

CREATE OR REPLACE FUNCTION billing.fn_issue_initial_invoice(
    p_subscription_id uuid,
    p_operator_id     text
) RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
    v_invoice_id   uuid;
    v_tenant_id    uuid;
    v_amount       numeric(18,2);
    v_currency     text;
BEGIN
    -- Проверяем, что подписка существует и получаем базовые параметры
    SELECT s.tenant_id,
           COALESCE(s.amount, 0.00) AS amount,
           s.currency_code
    INTO   v_tenant_id,
           v_amount,
           v_currency
    FROM billing.subscription s
    WHERE s.subscription_id = p_subscription_id;

    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'Subscription % not found', p_subscription_id;
    END IF;

    -- Временно: если amount NULL, считаем 0.00 RUB и помечаем это в meta
    IF v_amount IS NULL THEN
        v_amount := 0.00;
    END IF;

    IF v_currency IS NULL THEN
        v_currency := 'RUB';
    END IF;

    INSERT INTO billing.invoice (
        subscription_id,
        tenant_id,
        status,
        amount,
        currency_code,
        due_date,
        meta,
        created_by,
        updated_by
    )
    VALUES (
        p_subscription_id,
        v_tenant_id,
        'issued',
        v_amount,
        v_currency,
        current_date + 7,                     -- условно, 7 дней на оплату
        jsonb_build_object(
            'initial', true
        ),
        p_operator_id,
        p_operator_id
    )
    RETURNING invoice_id INTO v_invoice_id;

    RETURN v_invoice_id;
END;
$$;

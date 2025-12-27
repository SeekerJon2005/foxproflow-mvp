-- 20251208_dev_dev_order_link_core_v1.sql
-- Добавляет dev.dev_order_link, функции fn_dev_order_link_*
-- и обновляет dev.v_dev_order_commercial_ctx под таблицу линков.
-- NDC: только IF NOT EXISTS / CREATE OR REPLACE.

BEGIN;

CREATE SCHEMA IF NOT EXISTS dev;

-------------------------------
-- 1. Таблица dev.dev_order_link
-------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'dev'
          AND table_name   = 'dev_order_link'
    ) THEN
        CREATE TABLE dev.dev_order_link (
            -- Ссылка на dev.dev_order.dev_order_id
            order_id       uuid NOT NULL
                REFERENCES dev.dev_order(dev_order_id) ON DELETE CASCADE,

            -- тип связи:
            --   'crm_tenant' | 'billing_subscription' | 'billing_invoice' | 'crm_lead' | ...
            link_type      text NOT NULL,

            -- прямой FK только к tenant (ядро мультиарендности)
            crm_tenant_id  uuid NULL,

            -- произвольная ссылка (таблица/id и доп. атрибуты)
            external_ref   jsonb NOT NULL DEFAULT '{}'::jsonb,

            created_at     timestamptz NOT NULL DEFAULT now(),
            created_by     text NOT NULL,

            PRIMARY KEY (order_id, link_type)
        );
    END IF;
END
$$;

-- 1.1. Опциональный FK на crm.tenant, если таблица уже есть
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'crm'
          AND table_name   = 'tenant'
    ) THEN
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.table_constraints tc
            WHERE tc.table_schema    = 'dev'
              AND tc.table_name      = 'dev_order_link'
              AND tc.constraint_name = 'dev_order_link_crm_tenant_fk'
        ) THEN
            ALTER TABLE dev.dev_order_link
            ADD CONSTRAINT dev_order_link_crm_tenant_fk
            FOREIGN KEY (crm_tenant_id) REFERENCES crm.tenant(id);
        END IF;
    END IF;
END
$$;

-------------------------------
-- 2. Функции линковки
-------------------------------

-- 2.1. Привязка к tenant (crm.tenant)
CREATE OR REPLACE FUNCTION dev.fn_dev_order_link_to_tenant(
    p_order_id  uuid,
    p_tenant_id uuid,
    p_actor     text
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dev.dev_order_link(order_id, link_type, crm_tenant_id, external_ref, created_by)
    VALUES (p_order_id, 'crm_tenant', p_tenant_id, '{}'::jsonb, p_actor)
    ON CONFLICT (order_id, link_type) DO UPDATE
    SET crm_tenant_id = EXCLUDED.crm_tenant_id,
        created_at    = now(),
        created_by    = EXCLUDED.created_by;
END;
$$;

-- 2.2. Привязка к billing.* (subscription/invoice)
CREATE OR REPLACE FUNCTION dev.fn_dev_order_link_to_billing(
    p_order_id      uuid,
    p_link_type     text,   -- 'billing_subscription' | 'billing_invoice' | ...
    p_billing_table text,   -- 'billing.subscription', 'billing.invoice', ...
    p_billing_id    uuid,
    p_actor         text
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dev.dev_order_link(order_id, link_type, crm_tenant_id, external_ref, created_by)
    VALUES (
        p_order_id,
        p_link_type,
        NULL,
        jsonb_build_object(
            'billing_table', p_billing_table,
            'billing_id',    p_billing_id
        ),
        p_actor
    )
    ON CONFLICT (order_id, link_type) DO UPDATE
    SET external_ref = EXCLUDED.external_ref,
        created_at   = now(),
        created_by   = EXCLUDED.created_by;
END;
$$;

-- 2.3. Привязка к CRM-lead (внешний код лида/сделки)
CREATE OR REPLACE FUNCTION dev.fn_dev_order_link_to_crm_lead(
    p_order_id  uuid,
    p_lead_code text,
    p_actor     text
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dev.dev_order_link(order_id, link_type, crm_tenant_id, external_ref, created_by)
    VALUES (
        p_order_id,
        'crm_lead',
        NULL,
        jsonb_build_object('lead_code', p_lead_code),
        p_actor
    )
    ON CONFLICT (order_id, link_type) DO UPDATE
    SET external_ref = EXCLUDED.external_ref,
        created_at   = now(),
        created_by   = EXCLUDED.created_by;
END;
$$;

-------------------------------
-- 3. Обновляем витрину dev.v_dev_order_commercial_ctx
--    чтобы использовать dev_order_link
-------------------------------

CREATE OR REPLACE VIEW dev.v_dev_order_commercial_ctx AS
SELECT
    o.dev_order_id,

    o.created_at AS order_created_at,
    o.updated_at AS order_updated_at,
    o.status     AS order_status,
    o.title      AS order_title,
    o.description AS order_description,

    o.customer_name,
    o.total_amount,
    o.currency_code,

    -- внешний id тенанта из dev.dev_order
    o.tenant_id AS order_tenant_external_id,

    -- CRM-tenant (id, без детализации кода/имени на этом этапе)
    lt.crm_tenant_id,
    NULL::text AS tenant_code,
    NULL::text AS tenant_name,

    -- Billing (разбираем external_ref -> billing_table/billing_id)
    (ls.external_ref ->> 'billing_table')::text AS billing_subscription_table,
    (ls.external_ref ->> 'billing_id')::uuid    AS billing_subscription_id,
    (li.external_ref ->> 'billing_table')::text AS billing_invoice_table,
    (li.external_ref ->> 'billing_id')::uuid    AS billing_invoice_id,

    -- CRM lead (код лида в CRM)
    (ll.external_ref ->> 'lead_code')::text     AS crm_lead_code
FROM dev.dev_order o
LEFT JOIN dev.dev_order_link lt
    ON lt.order_id = o.dev_order_id AND lt.link_type = 'crm_tenant'
LEFT JOIN dev.dev_order_link ls
    ON ls.order_id = o.dev_order_id AND ls.link_type = 'billing_subscription'
LEFT JOIN dev.dev_order_link li
    ON li.order_id = o.dev_order_id AND li.link_type = 'billing_invoice'
LEFT JOIN dev.dev_order_link ll
    ON ll.order_id = o.dev_order_id AND ll.link_type = 'crm_lead';

COMMIT;

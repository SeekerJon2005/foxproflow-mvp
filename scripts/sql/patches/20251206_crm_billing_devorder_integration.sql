-- 20251206_crm_billing_devorder_integration.sql
-- NDC-патч: интеграция dev.dev_order с CRM/Billing без ломающих изменений.
-- stack=sql
-- goal=Связать dev-заказы с tenant и биллинг-сущностями; дать удобное представление.
-- summary=Добавляет dev.dev_order_link и функции fn_dev_order_link_* + view v_dev_order_commercial_ctx.

-------------------------------
-- 0. Гигиена и схемы
-------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'dev'
    ) THEN
        EXECUTE 'CREATE SCHEMA dev';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'crm'
    ) THEN
        EXECUTE 'CREATE SCHEMA crm';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'billing'
    ) THEN
        EXECUTE 'CREATE SCHEMA billing';
    END IF;
END
$$;

-------------------------------
-- 1. Таблица связей dev_order ↔ CRM/Billing
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
            -- 'crm_tenant' | 'billing_subscription' | 'billing_invoice' | 'crm_lead' | ...
            link_type      text NOT NULL,

            -- прямой FK только к tenant (ядро мультиарендности)
            -- crm.tenant.id (uuid)
            crm_tenant_id  uuid NULL
                REFERENCES crm.tenant(id),

            -- произвольная ссылка (таблица/id и доп. атрибуты)
            external_ref   jsonb NOT NULL DEFAULT '{}'::jsonb,

            created_at     timestamptz NOT NULL DEFAULT now(),
            created_by     text NOT NULL,

            PRIMARY KEY (order_id, link_type)
        );
    END IF;
END
$$;

-------------------------------
-- 2. Функции линковки
-------------------------------

-- 2.1. Привязка к tenant

CREATE OR REPLACE FUNCTION dev.fn_dev_order_link_to_tenant(
    p_order_id   uuid,
    p_tenant_id  uuid,
    p_actor      text
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

-- 2.2. Привязка к Billing (subscription / invoice и т.п.)

CREATE OR REPLACE FUNCTION dev.fn_dev_order_link_to_billing(
    p_order_id       uuid,
    p_link_type      text,  -- 'billing_subscription' | 'billing_invoice' | ...
    p_billing_table  text,  -- 'billing.subscription', 'billing.invoice', ...
    p_billing_id     uuid,
    p_actor          text
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
            'table', p_billing_table,
            'id',    p_billing_id::text
        ),
        p_actor
    )
    ON CONFLICT (order_id, link_type) DO UPDATE
    SET external_ref = EXCLUDED.external_ref,
        created_at   = now(),
        created_by   = EXCLUDED.created_by;
END;
$$;

-- 2.3. Привязка к CRM-лиду по внешнему коду

CREATE OR REPLACE FUNCTION dev.fn_dev_order_link_to_crm_lead(
    p_order_id    uuid,
    p_lead_code   text,  -- внешний код лида/deal в CRM v2
    p_actor       text
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dev.dev_order_link(order_id, link_type, crm_tenant_id, external_ref, created_by)
    VALUES (
        p_order_id,
        'crm_lead',
        NULL,
        jsonb_build_object(
            'lead_code', p_lead_code
        ),
        p_actor
    )
    ON CONFLICT (order_id, link_type) DO UPDATE
    SET external_ref = EXCLUDED.external_ref,
        created_at   = now(),
        created_by   = EXCLUDED.created_by;
END;
$$;

-------------------------------
-- 3. View dev.v_dev_order_commercial_ctx
--    адаптирован под фактическую схему:
--    dev.dev_order(dev_order_id, title, status, total_amount, currency_code, customer_name, tenant_id, ...)
--    crm.tenant(id, code, name, ...)
-------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.views
        WHERE table_schema = 'dev'
          AND table_name   = 'v_dev_order_commercial_ctx'
    ) THEN
        EXECUTE 'DROP VIEW dev.v_dev_order_commercial_ctx';
    END IF;

    EXECUTE $view$
        CREATE VIEW dev.v_dev_order_commercial_ctx AS
        SELECT
            o.dev_order_id,
            o.created_at           AS order_created_at,
            o.updated_at           AS order_updated_at,
            o.status               AS order_status,
            o.title                AS order_title,
            o.description          AS order_description,
            o.customer_name,
            o.total_amount,
            o.currency_code,
            -- внешняя текстовая привязка из старой схемы, если используется
            o.tenant_id            AS order_tenant_external_id,

            lt.crm_tenant_id,
            t.code                 AS tenant_code,
            t.name                 AS tenant_name,

            -- подписка
            ls.external_ref ->> 'table' AS billing_subscription_table,
            ls.external_ref ->> 'id'    AS billing_subscription_id,

            -- инвойс
            li.external_ref ->> 'table' AS billing_invoice_table,
            li.external_ref ->> 'id'    AS billing_invoice_id,

            -- CRM-лид
            ll.external_ref ->> 'lead_code' AS crm_lead_code
        FROM dev.dev_order o
        LEFT JOIN dev.dev_order_link lt
               ON lt.order_id  = o.dev_order_id
              AND lt.link_type = 'crm_tenant'
        LEFT JOIN crm.tenant t
               ON t.id         = lt.crm_tenant_id
        LEFT JOIN dev.dev_order_link ls
               ON ls.order_id  = o.dev_order_id
              AND ls.link_type = 'billing_subscription'
        LEFT JOIN dev.dev_order_link li
               ON li.order_id  = o.dev_order_id
              AND li.link_type = 'billing_invoice'
        LEFT JOIN dev.dev_order_link ll
               ON ll.order_id  = o.dev_order_id
              AND ll.link_type = 'crm_lead';
    $view$;
END
$$;

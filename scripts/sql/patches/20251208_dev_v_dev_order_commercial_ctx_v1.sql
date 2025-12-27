-- 20251208_dev_v_dev_order_commercial_ctx_v1.sql
-- Базовая витрина dev.v_dev_order_commercial_ctx для DevOrders.
-- На этом этапе даём только данные из dev.dev_order, остальные поля-заглушки NULL.
-- Позже вьюха может быть расширена джойнами к CRM / Billing / leads.

BEGIN;

CREATE SCHEMA IF NOT EXISTS dev;

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

    -- внешний идентификатор tenant’а из dev.dev_order
    o.tenant_id  AS order_tenant_external_id,

    -- CRM-tenant (пока заглушки)
    NULL::uuid AS crm_tenant_id,
    NULL::text AS tenant_code,
    NULL::text AS tenant_name,

    -- Billing (пока заглушки)
    NULL::text AS billing_subscription_table,
    NULL::uuid AS billing_subscription_id,
    NULL::text AS billing_invoice_table,
    NULL::uuid AS billing_invoice_id,

    -- CRM lead (логическая привязка, пока заглушка)
    NULL::text AS crm_lead_code
FROM dev.dev_order o;

COMMIT;

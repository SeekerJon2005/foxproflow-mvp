BEGIN;

-- === БАЗОВАЯ dev.dev_order (если ещё нет) ===
-- Канонический PK: dev_order_id uuid (как уже есть у тебя)
CREATE TABLE IF NOT EXISTS dev.dev_order (
  dev_order_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id                uuid           NOT NULL DEFAULT gen_random_uuid(),
  title                    text,
  description              text,
  customer_name            text,
  order_tenant_external_id text,
  total_amount             numeric(18, 2),
  currency_code            text,
  status                   text           DEFAULT 'new',
  created_at               timestamptz    DEFAULT now(),
  updated_at               timestamptz    DEFAULT now()
);

-- Доводим существующую dev.dev_order до нужной схемы (тип dev_order_id НЕ трогаем)
ALTER TABLE dev.dev_order
  ADD COLUMN IF NOT EXISTS public_id                uuid        NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS title                    text,
  ADD COLUMN IF NOT EXISTS description              text,
  ADD COLUMN IF NOT EXISTS customer_name            text,
  ADD COLUMN IF NOT EXISTS order_tenant_external_id text,
  ADD COLUMN IF NOT EXISTS total_amount             numeric(18, 2),
  ADD COLUMN IF NOT EXISTS currency_code            text,
  ADD COLUMN IF NOT EXISTS status                   text        DEFAULT 'new',
  ADD COLUMN IF NOT EXISTS created_at               timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at               timestamptz DEFAULT now();

COMMENT ON TABLE dev.dev_order IS
  'DevFactory DevOrders: коммерческие заказы, которые связывают DevFactory, CRM и Billing';


-- === dev.dev_order_link: связи DevOrder ↔ CRM/Billing/Lead ===

-- Если таблицы нет — создаём каркас
CREATE TABLE IF NOT EXISTS dev.dev_order_link (
  id bigserial PRIMARY KEY
);

-- Чистим старый, неправильный dev_order_id (если был bigint)
ALTER TABLE dev.dev_order_link
  DROP COLUMN IF EXISTS dev_order_id;

-- Теперь доводим до нужной схемы
ALTER TABLE dev.dev_order_link
  ADD COLUMN IF NOT EXISTS dev_order_id uuid,
  ADD COLUMN IF NOT EXISTS link_type   text,
  ADD COLUMN IF NOT EXISTS ref_table   text,
  ADD COLUMN IF NOT EXISTS ref_id      text,
  ADD COLUMN IF NOT EXISTS created_at  timestamptz NOT NULL DEFAULT now();

-- Подстраховка для link_type (чтоб не было NULL)
UPDATE dev.dev_order_link
SET link_type = COALESCE(link_type, 'tenant');

COMMENT ON TABLE dev.dev_order_link IS
  'Связи DevOrder с CRM/Billing/Lead (tenant, подписка, счёт, лид и т.п.)';


-- === View: коммерческий контекст DevOrder для DevOrders Console ===

-- Старый view мог иметь другую схему колонок, поэтому его надо просто снести
DROP VIEW IF EXISTS dev.v_dev_order_commercial_ctx;

CREATE VIEW dev.v_dev_order_commercial_ctx AS
SELECT
  o.dev_order_id          AS dev_order_id,
  o.public_id             AS dev_order_public_id,
  o.title                 AS order_title,
  o.description           AS order_description,
  o.customer_name,
  o.order_tenant_external_id,
  o.total_amount,
  o.currency_code,
  o.status                AS order_status,
  o.created_at            AS order_created_at,
  o.updated_at            AS order_updated_at,

  -- tenant
  MAX(CASE WHEN l.link_type = 'tenant' THEN l.ref_table END) AS crm_tenant_table,
  MAX(CASE WHEN l.link_type = 'tenant' THEN l.ref_id    END) AS crm_tenant_id,

  -- billing.subscription
  MAX(CASE WHEN l.link_type = 'billing_subscription' THEN l.ref_table END) AS billing_subscription_table,
  MAX(CASE WHEN l.link_type = 'billing_subscription' THEN l.ref_id    END) AS billing_subscription_id,

  -- billing.invoice
  MAX(CASE WHEN l.link_type = 'billing_invoice' THEN l.ref_table END) AS billing_invoice_table,
  MAX(CASE WHEN l.link_type = 'billing_invoice' THEN l.ref_id    END) AS billing_invoice_id,

  -- lead
  MAX(CASE WHEN l.link_type = 'lead' THEN l.ref_id END) AS crm_lead_code
FROM dev.dev_order AS o
LEFT JOIN dev.dev_order_link AS l
  ON l.dev_order_id = o.dev_order_id
GROUP BY
  o.dev_order_id,
  o.public_id,
  o.title,
  o.description,
  o.customer_name,
  o.order_tenant_external_id,
  o.total_amount,
  o.currency_code,
  o.status,
  o.created_at,
  o.updated_at;

COMMENT ON VIEW dev.v_dev_order_commercial_ctx IS
  'Коммерческий контекст DevOrder: основное тело заказа + связи с tenant/billing/lead';

COMMIT;

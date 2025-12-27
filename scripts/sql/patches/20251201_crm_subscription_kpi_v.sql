-- CRM / Billing KPI view по подпискам
-- Собираем картину по crm.subscriptions (v1) и crm.subscription (v2).
-- NDC: только CREATE VIEW IF NOT EXISTS, никакого DROP.

CREATE SCHEMA IF NOT EXISTS crm;

-- Aggregated KPI по v1-подпискам (crm.subscriptions)
CREATE OR REPLACE VIEW crm.subscription_kpi_v AS
WITH v1 AS (
    SELECT
        s.product_code,
        s.plan_code,
        s.status,
        s.billing_period,
        s.currency,
        COUNT(*)                       AS cnt_v1,
        COALESCE(SUM(s.amount_month),0) AS mrr_v1
    FROM crm.subscriptions s
    GROUP BY
        s.product_code,
        s.plan_code,
        s.status,
        s.billing_period,
        s.currency
),
v2 AS (
    SELECT
        NULL::text                     AS product_code, -- v2 не хранит product_code
        s.plan_code,
        s.status,
        s.billing_period,
        s.currency,
        COUNT(*)                       AS cnt_v2,
        COALESCE(SUM(s.amount),0)     AS mrr_v2
    FROM crm.subscription s
    GROUP BY
        s.plan_code,
        s.status,
        s.billing_period,
        s.currency
)
SELECT
    COALESCE(v1.product_code, v2.product_code) AS product_code,
    COALESCE(v1.plan_code,    v2.plan_code)    AS plan_code,
    COALESCE(v1.status,       v2.status)       AS status,
    COALESCE(v1.billing_period, v2.billing_period) AS billing_period,
    COALESCE(v1.currency,     v2.currency)     AS currency,
    COALESCE(v1.cnt_v1, 0)                     AS cnt_v1,
    COALESCE(v2.cnt_v2, 0)                     AS cnt_v2,
    COALESCE(v1.cnt_v1, 0) + COALESCE(v2.cnt_v2, 0) AS cnt_total,
    COALESCE(v1.mrr_v1, 0)                     AS mrr_v1,
    COALESCE(v2.mrr_v2, 0)                     AS mrr_v2,
    COALESCE(v1.mrr_v1, 0) + COALESCE(v2.mrr_v2, 0) AS mrr_total
FROM v1
FULL JOIN v2
  ON v1.plan_code      = v2.plan_code
 AND v1.status         = v2.status
 AND v1.billing_period = v2.billing_period
 AND v1.currency       = v2.currency;

COMMENT ON VIEW crm.subscription_kpi_v IS
    'Aggregated KPI по подпискам (v1: crm.subscriptions, v2: crm.subscription): count и MRR по продукту/плану/статусу.';

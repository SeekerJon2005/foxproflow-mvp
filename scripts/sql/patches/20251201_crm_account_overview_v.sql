-- CRM / Account overview view
-- Объединяем accounts + subscriptions (v1) + subscription (v2) в один срез.
-- NDC: только CREATE VIEW, никаких DROP.

CREATE SCHEMA IF NOT EXISTS crm;

CREATE OR REPLACE VIEW crm.account_overview_v AS
SELECT
    a.id                         AS account_id,
    a.tenant_id                  AS tenant_id,
    a.company_name               AS company_name,
    a.country                    AS country,
    a.region                     AS region,
    a.created_at                 AS account_created_at,
    a.updated_at                 AS account_updated_at,

    s.id                         AS subscription_id_v1,
    s.product_code               AS product_code,
    s.plan_code                  AS plan_code,
    s.status                     AS subscription_status_v1,
    s.billing_period             AS billing_period_v1,
    s.currency                   AS currency_v1,
    s.amount_month               AS amount_month_v1,
    s.started_at                 AS started_at_v1,
    s.trial_ends_at              AS trial_ends_at_v1,
    s.expires_at                 AS expires_at_v1,

    s2.id                        AS subscription_id_v2,
    s2.status                    AS subscription_status_v2,
    s2.billing_period            AS billing_period_v2,
    s2.currency                  AS currency_v2,
    s2.amount                    AS amount_v2,
    s2.starts_at                 AS starts_at_v2,
    s2.trial_until               AS trial_until_v2,
    s2.ends_at                   AS ends_at_v2

FROM crm.accounts a
LEFT JOIN crm.subscriptions s
       ON s.account_id = a.id
LEFT JOIN crm.subscription s2
       ON s2.tenant_id = a.tenant_id
      AND (
           s.plan_code IS NULL
           OR s2.plan_code = s.plan_code
          );

COMMENT ON VIEW crm.account_overview_v IS
    'Обзорная витрина по аккаунтам CRM: accounts + crm.subscriptions (v1) + crm.subscription (v2).';

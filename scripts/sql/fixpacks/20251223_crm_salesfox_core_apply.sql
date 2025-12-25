-- 20251223_crm_salesfox_core_apply.sql
-- FoxProFlow • FixPack • CRM SalesFox core (DB contract for B-dev)
-- Purpose:
--   Provide minimal CRM schema for SalesFox:
--     - crm.leads
--     - crm.sales_sessions
--     - crm.accounts
--     - crm.subscriptions_v1 / crm.subscriptions_v2
--     - crm.onboarding_sessions
--     - crm.account_overview_v
--     - crm.trial_accounts_overview_v
--     - crm.fn_lead_win_trial_and_onboarding(...)
-- Notes:
--   - Idempotent style (IF NOT EXISTS / OR REPLACE).
--   - Avoid strict CHECK constraints for channel/status to prevent mismatch with code constants.
--   - UUID generation: best-effort via pgcrypto/uuid-ossp, fallback via md5-based generator.
--
-- Apply via psql with ON_ERROR_STOP=1.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858380);

BEGIN;

CREATE SCHEMA IF NOT EXISTS crm;

-- Best-effort extensions (do NOT fail if privileges are limited)
DO $$
BEGIN
  BEGIN
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS pgcrypto';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'warn: pgcrypto not available (%). Will use fallback UUID generator.', SQLERRM;
  END;

  BEGIN
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'warn: uuid-ossp not available (%).', SQLERRM;
  END;
END $$;

-- UUID helper (fallback-safe)
CREATE OR REPLACE FUNCTION crm.ff_uuid_v4()
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
  v uuid;
  h text;
BEGIN
  -- best: pgcrypto
  BEGIN
    EXECUTE 'SELECT gen_random_uuid()' INTO v;
    IF v IS NOT NULL THEN
      RETURN v;
    END IF;
  EXCEPTION WHEN undefined_function THEN
    NULL;
  END;

  -- second best: uuid-ossp
  BEGIN
    EXECUTE 'SELECT uuid_generate_v4()' INTO v;
    IF v IS NOT NULL THEN
      RETURN v;
    END IF;
  EXCEPTION WHEN undefined_function THEN
    NULL;
  END;

  -- fallback: md5-based (format into uuid)
  h := md5(random()::text || clock_timestamp()::text || random()::text);
  v := (substr(h,1,8) || '-' || substr(h,9,4) || '-' || substr(h,13,4) || '-' || substr(h,17,4) || '-' || substr(h,21,12))::uuid;
  RETURN v;
END $$;

-- =========================
-- Core tables
-- =========================

-- Tenants (minimal)
CREATE TABLE IF NOT EXISTS crm.tenants (
  id          uuid        PRIMARY KEY DEFAULT crm.ff_uuid_v4(),
  created_at  timestamptz NOT NULL    DEFAULT now()
);

-- Leads (used by tasks_salesfox.py and routers/crm.py)
CREATE TABLE IF NOT EXISTS crm.leads (
  id              bigserial PRIMARY KEY,
  source          text        NULL,
  status          text        NOT NULL DEFAULT 'new',
  company_name    text        NULL,
  contact_name    text        NULL,
  email           text        NULL,
  phone           text        NULL,
  country         text        NULL,
  region          text        NULL,
  payload         jsonb       NOT NULL DEFAULT '{}'::jsonb,
  last_session_id bigint      NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_leads_status_idx     ON crm.leads (status);
CREATE INDEX IF NOT EXISTS crm_leads_created_at_idx ON crm.leads (created_at DESC);
CREATE INDEX IF NOT EXISTS crm_leads_updated_at_idx ON crm.leads (updated_at DESC);

-- Sales sessions (used by tasks_salesfox.py and routers/sales.py)
CREATE TABLE IF NOT EXISTS crm.sales_sessions (
  id            bigserial PRIMARY KEY,
  lead_id       bigint      NOT NULL,
  channel       text        NOT NULL,
  status        text        NOT NULL DEFAULT 'active',
  transcript    jsonb       NOT NULL DEFAULT '[]'::jsonb,
  summary       jsonb       NOT NULL DEFAULT '{}'::jsonb,
  last_event_id bigint      NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_sales_sessions_lead_id_idx    ON crm.sales_sessions (lead_id);
CREATE INDEX IF NOT EXISTS crm_sales_sessions_status_idx     ON crm.sales_sessions (status);
CREATE INDEX IF NOT EXISTS crm_sales_sessions_created_at_idx ON crm.sales_sessions (created_at DESC);

-- Accounts (minimal; one account per lead for now)
CREATE TABLE IF NOT EXISTS crm.accounts (
  id           bigserial PRIMARY KEY,
  tenant_id    uuid        NOT NULL,
  lead_id      bigint      NOT NULL,
  company_name text        NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_accounts_lead_id ON crm.accounts (lead_id);
CREATE INDEX IF NOT EXISTS ix_crm_accounts_tenant_id     ON crm.accounts (tenant_id);

-- Subscription v1 (int id)
CREATE TABLE IF NOT EXISTS crm.subscriptions_v1 (
  id             bigserial PRIMARY KEY,
  account_id     bigint      NOT NULL,
  product_code   text        NOT NULL,
  plan_code      text        NOT NULL,
  currency       text        NOT NULL,
  amount_month   numeric     NOT NULL DEFAULT 0,
  billing_period text        NOT NULL DEFAULT 'monthly',
  trial_ends_at  timestamptz NULL,
  status         text        NOT NULL DEFAULT 'trial',
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_crm_sub_v1_account_id     ON crm.subscriptions_v1 (account_id);
CREATE INDEX IF NOT EXISTS ix_crm_sub_v1_trial_ends_at  ON crm.subscriptions_v1 (trial_ends_at);

-- Subscription v2 (uuid id)
CREATE TABLE IF NOT EXISTS crm.subscriptions_v2 (
  id             uuid        PRIMARY KEY DEFAULT crm.ff_uuid_v4(),
  account_id     bigint      NOT NULL,
  product_code   text        NOT NULL,
  plan_code      text        NOT NULL,
  currency       text        NOT NULL,
  amount_month   numeric     NOT NULL DEFAULT 0,
  billing_period text        NOT NULL DEFAULT 'monthly',
  trial_until    timestamptz NULL,
  status         text        NOT NULL DEFAULT 'trial',
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_crm_sub_v2_account_id    ON crm.subscriptions_v2 (account_id);
CREATE INDEX IF NOT EXISTS ix_crm_sub_v2_trial_until   ON crm.subscriptions_v2 (trial_until);

-- Onboarding sessions
CREATE TABLE IF NOT EXISTS crm.onboarding_sessions (
  id         bigserial PRIMARY KEY,
  account_id bigint      NOT NULL,
  lead_id    bigint      NOT NULL,
  status     text        NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_crm_onboarding_account_id ON crm.onboarding_sessions (account_id);
CREATE INDEX IF NOT EXISTS ix_crm_onboarding_lead_id    ON crm.onboarding_sessions (lead_id);

-- =========================
-- Views used by B-dev
-- =========================

-- account_overview_v (used by tasks_salesfox.py)
CREATE OR REPLACE VIEW crm.account_overview_v AS
SELECT
  a.id AS account_id,
  a.company_name,
  a.tenant_id,
  s2.trial_until AS trial_until_v2,
  s1.trial_ends_at AS trial_ends_at_v1
FROM crm.accounts a
LEFT JOIN LATERAL (
  SELECT s2.*
  FROM crm.subscriptions_v2 s2
  WHERE s2.account_id = a.id
  ORDER BY s2.created_at DESC
  LIMIT 1
) s2 ON true
LEFT JOIN LATERAL (
  SELECT s1.*
  FROM crm.subscriptions_v1 s1
  WHERE s1.account_id = a.id
  ORDER BY s1.created_at DESC
  LIMIT 1
) s1 ON true;

-- trial_accounts_overview_v (used by routers/crm.py)
CREATE OR REPLACE VIEW crm.trial_accounts_overview_v AS
WITH base AS (
  SELECT
    a.id AS account_id,
    a.company_name,
    COALESCE(s2.product_code, s1.product_code) AS product_code,
    COALESCE(s2.plan_code,   s1.plan_code)     AS plan_code,
    COALESCE(s2.trial_until, s1.trial_ends_at) AS trial_until
  FROM crm.accounts a
  LEFT JOIN LATERAL (
    SELECT s2.*
    FROM crm.subscriptions_v2 s2
    WHERE s2.account_id = a.id
    ORDER BY s2.created_at DESC
    LIMIT 1
  ) s2 ON true
  LEFT JOIN LATERAL (
    SELECT s1.*
    FROM crm.subscriptions_v1 s1
    WHERE s1.account_id = a.id
    ORDER BY s1.created_at DESC
    LIMIT 1
  ) s1 ON true
)
SELECT
  account_id,
  COALESCE(company_name,'') AS company_name,
  COALESCE(product_code,'') AS product_code,
  COALESCE(plan_code,'')    AS plan_code,
  trial_until,
  (trial_until IS NOT NULL AND trial_until < now()) AS is_expired,
  CASE
    WHEN trial_until IS NULL THEN 'none'
    WHEN trial_until < now() THEN 'expired'
    WHEN trial_until <= now() + interval '3 days' THEN 'expiring_soon'
    ELSE 'active'
  END AS trial_status,
  CASE
    WHEN trial_until IS NULL THEN 0
    ELSE GREATEST(
      0,
      CEIL(EXTRACT(EPOCH FROM (trial_until - now())) / 86400.0)::int
    )
  END AS days_left
FROM base;

-- =========================
-- Orchestrator function (used by B-dev)
-- =========================

CREATE OR REPLACE FUNCTION crm.fn_lead_win_trial_and_onboarding(
  p_lead_id       bigint,
  p_product_code  text,
  p_plan_code     text,
  p_currency      text,
  p_amount_month  numeric,
  p_billing_period text,
  p_trial_days    integer
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
AS $$
DECLARE
  v_payload    jsonb;
  v_company    text;
  v_tenant     uuid;
  v_account_id bigint;
  v_sub1_id    bigint;
  v_sub2_id    uuid;
  v_onb_id     bigint;
  v_trial_until timestamptz;
BEGIN
  -- 0) Lead must exist; if not found -> return 0 rows (caller treats as "not processed")
  SELECT l.payload, l.company_name
  INTO v_payload, v_company
  FROM crm.leads l
  WHERE l.id = p_lead_id;

  IF NOT FOUND THEN
    RETURN;
  END IF;

  -- 1) tenant_id in payload (generate if missing)
  v_tenant := NULL;
  BEGIN
    v_tenant := NULLIF(v_payload->>'tenant_id','')::uuid;
  EXCEPTION WHEN OTHERS THEN
    v_tenant := NULL;
  END;

  IF v_tenant IS NULL THEN
    v_tenant := crm.ff_uuid_v4();
    v_payload := jsonb_set(coalesce(v_payload,'{}'::jsonb), '{tenant_id}', to_jsonb(v_tenant::text), true);

    UPDATE crm.leads
    SET payload = v_payload,
        updated_at = now()
    WHERE id = p_lead_id;
  END IF;

  -- 2) ensure tenant record
  INSERT INTO crm.tenants(id)
  VALUES (v_tenant)
  ON CONFLICT (id) DO NOTHING;

  -- 3) mark lead won
  UPDATE crm.leads
  SET status = 'won',
      updated_at = now()
  WHERE id = p_lead_id;

  -- 4) account (one per lead)
  SELECT a.id
  INTO v_account_id
  FROM crm.accounts a
  WHERE a.lead_id = p_lead_id;

  IF v_account_id IS NULL THEN
    INSERT INTO crm.accounts(tenant_id, lead_id, company_name)
    VALUES (v_tenant, p_lead_id, v_company)
    RETURNING id INTO v_account_id;
  ELSE
    UPDATE crm.accounts
    SET tenant_id = v_tenant,
        updated_at = now()
    WHERE id = v_account_id;
  END IF;

  -- 5) trial timestamps
  v_trial_until := now() + make_interval(days => GREATEST(COALESCE(p_trial_days, 0), 0));

  -- 6) create v1 subscription (simple)
  INSERT INTO crm.subscriptions_v1(
    account_id, product_code, plan_code, currency, amount_month, billing_period, trial_ends_at, status
  )
  VALUES (
    v_account_id,
    COALESCE(p_product_code,'logistics'),
    COALESCE(p_plan_code,'mvp-5-15-trucks'),
    COALESCE(p_currency,'RUB'),
    COALESCE(p_amount_month, 0),
    COALESCE(p_billing_period,'monthly'),
    v_trial_until,
    'trial'
  )
  RETURNING id INTO v_sub1_id;

  -- 7) create v2 subscription (uuid)
  INSERT INTO crm.subscriptions_v2(
    account_id, product_code, plan_code, currency, amount_month, billing_period, trial_until, status
  )
  VALUES (
    v_account_id,
    COALESCE(p_product_code,'logistics'),
    COALESCE(p_plan_code,'mvp-5-15-trucks'),
    COALESCE(p_currency,'RUB'),
    COALESCE(p_amount_month, 0),
    COALESCE(p_billing_period,'monthly'),
    v_trial_until,
    'trial'
  )
  RETURNING id INTO v_sub2_id;

  -- 8) onboarding session
  INSERT INTO crm.onboarding_sessions(account_id, lead_id, status)
  VALUES (v_account_id, p_lead_id, 'active')
  RETURNING id INTO v_onb_id;

  -- 9) return row
  lead_id_out        := p_lead_id;
  tenant_id_out      := v_tenant;
  account_id_out     := v_account_id;
  subscription_id    := v_sub1_id;
  subscription_v2_id := v_sub2_id;
  onboarding_id      := v_onb_id;

  RETURN NEXT;
END $$;

COMMIT;

SELECT pg_advisory_unlock(74858380);

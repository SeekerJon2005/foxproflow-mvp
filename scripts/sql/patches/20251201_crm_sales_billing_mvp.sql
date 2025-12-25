-- CRM / Sales / Billing MVP core schema
-- NDC: только CREATE IF NOT EXISTS, никаких DROP/разрушающих ALTER.

CREATE SCHEMA IF NOT EXISTS crm;

-- Клиенты FoxProFlow (тенанты)
CREATE TABLE IF NOT EXISTS crm.tenant (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    status       text        NOT NULL DEFAULT 'prospect', -- prospect/trial/active/suspended/churned
    code         text        UNIQUE,
    name         text        NOT NULL,
    full_name    text,
    segment      text,       -- small/medium/large и т.п.
    country_code text,
    timezone     text,
    tax_id       text,
    website      text,
    source       text,       -- канал: site/partner/referral и т.п.
    sales_owner  text,       -- ответственный SalesFox / менеджер
    config       jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE crm.tenant IS
    'Клиенты FoxProFlow (тенанты): статус, сегмент, базовые реквизиты.';

CREATE INDEX IF NOT EXISTS idx_crm_tenant_status_created_at
    ON crm.tenant (status, created_at DESC);

-- Контактные лица по тенанту
CREATE TABLE IF NOT EXISTS crm.tenant_contact (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    tenant_id    uuid        NOT NULL REFERENCES crm.tenant(id),
    role         text,       -- owner/logistics/finance/it/legal и т.п.
    full_name    text,
    email        text,
    phone        text,
    is_primary   boolean     NOT NULL DEFAULT false,
    notes        text
);

COMMENT ON TABLE crm.tenant_contact IS
    'Контактные лица по тенанту (владелец, логист, финдиректор и т.д.).';

CREATE INDEX IF NOT EXISTS idx_crm_tenant_contact_tenant_id_primary
    ON crm.tenant_contact (tenant_id, is_primary DESC, created_at DESC);

-- Лиды SalesFox
CREATE TABLE IF NOT EXISTS crm.lead (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    status              text        NOT NULL DEFAULT 'new', -- new/in_progress/won/lost/disqualified
    source              text,       -- site/landing/call/partner/...
    company_name        text,
    contact_name        text,
    contact_email       text,
    contact_phone       text,
    segment             text,       -- small/medium/large по парку
    fleet_size_min      integer,
    fleet_size_max      integer,
    has_tms             boolean,
    problems            text,       -- боль клиента в свободном виде
    estimated_profit_uplift_pct numeric(5,2), -- оценка роста прибыли, % (10.00 и т.п.)
    sales_owner         text,       -- ответственный менеджер
    converted_tenant_id uuid        REFERENCES crm.tenant(id),
    meta                jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE crm.lead IS
    'Входящие лиды SalesFox: параметры компании, статус и конверсия в тенанта.';

CREATE INDEX IF NOT EXISTS idx_crm_lead_status_created_at
    ON crm.lead (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crm_lead_converted_tenant
    ON crm.lead (converted_tenant_id)
    WHERE converted_tenant_id IS NOT NULL;

-- Подписки FoxProFlow по тенантам
CREATE TABLE IF NOT EXISTS crm.subscription (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    tenant_id       uuid        NOT NULL REFERENCES crm.tenant(id),
    status          text        NOT NULL DEFAULT 'trial',   -- trial/active/paused/cancelled/expired
    plan_code       text        NOT NULL,                   -- код тарифа (например, mvp-5-15-trucks)
    billing_period  text        NOT NULL DEFAULT 'monthly', -- monthly/yearly
    currency        text        NOT NULL DEFAULT 'RUB',
    amount          numeric(18,2) NOT NULL DEFAULT 0,
    starts_at       timestamptz,
    trial_until     timestamptz,
    ends_at         timestamptz,
    meta            jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE crm.subscription IS
    'Подписки FoxProFlow по тенантам: тариф, сумма, период, даты.';

CREATE INDEX IF NOT EXISTS idx_crm_subscription_tenant_status
    ON crm.subscription (tenant_id, status, created_at DESC);

-- Счета BillingFox
CREATE TABLE IF NOT EXISTS crm.invoice (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    tenant_id       uuid        NOT NULL REFERENCES crm.tenant(id),
    subscription_id uuid        REFERENCES crm.subscription(id),
    external_id     text,                     -- идентификатор в платёжном шлюзе/ЭДО
    number          text,                     -- человекочитаемый номер счёта
    amount          numeric(18,2) NOT NULL,
    currency        text        NOT NULL DEFAULT 'RUB',
    due_date        date,
    status          text        NOT NULL DEFAULT 'draft', -- draft/sent/paid/overdue/cancelled
    paid_at         timestamptz,
    meta            jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE crm.invoice IS
    'Счета BillingFox: сумма, статус оплаты, связь с тенантом и подпиской.';

CREATE INDEX IF NOT EXISTS idx_crm_invoice_tenant_status_created_at
    ON crm.invoice (tenant_id, status, created_at DESC);

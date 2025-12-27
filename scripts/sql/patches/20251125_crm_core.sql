-- 20251125_crm_core.sql
-- FoxProFlow — CRM-ядро: лиды, аккаунты, продукты, подписки.
-- NDC: только CREATE SCHEMA/TABLE/INDEX IF NOT EXISTS и CHECK/UNIQUE,
--      никаких DROP/ALTER COLUMN/DELETE.

CREATE SCHEMA IF NOT EXISTS crm;

-- 1. Лиды (потенциальные клиенты)
CREATE TABLE IF NOT EXISTS crm.leads (
    id             bigserial PRIMARY KEY,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    source         text        NOT NULL,            -- 'web','partner','manual',...
    status         text        NOT NULL CHECK (
        status IN ('new','qualified','proposal','won','lost')
    ),                                              -- статус воронки

    company_name   text,
    contact_name   text,
    email          text,
    phone          text,

    country        text,
    region         text,
    payload        jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- любые доп. данные

    last_session_id bigint,     -- crm.sales_sessions.id (ссылка логическая, без FK)
    notes          text
);

COMMENT ON TABLE crm.leads IS 'CRM: входящие лиды (источник, контакт, статус воронки).';
COMMENT ON COLUMN crm.leads.source IS 'Источник лида: web/partner/manual/...';
COMMENT ON COLUMN crm.leads.status IS 'Статус лида в воронке: new/qualified/proposal/won/lost.';

CREATE INDEX IF NOT EXISTS idx_crm_leads_status_created_at
    ON crm.leads(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crm_leads_email
    ON crm.leads(email)
    WHERE email IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_crm_leads_phone
    ON crm.leads(phone)
    WHERE phone IS NOT NULL;

-- 2. Аккаунты (клиенты в системе)
CREATE TABLE IF NOT EXISTS crm.accounts (
    id             bigserial PRIMARY KEY,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    tenant_id      uuid        NOT NULL,            -- ID тенанта в основной системе
    company_name   text,
    country        text,
    region         text,
    payload        jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE crm.accounts IS 'CRM: действующие аккаунты (клиенты/тенанты).';
COMMENT ON COLUMN crm.accounts.tenant_id IS 'Tenant ID в основной системе (multi-tenant слой).';

CREATE UNIQUE INDEX IF NOT EXISTS idx_crm_accounts_tenant_id
    ON crm.accounts(tenant_id);

-- 3. Продукты (логистика/бухгалтерия/юр/DevFactory)
CREATE TABLE IF NOT EXISTS crm.products (
    code          text PRIMARY KEY,      -- 'logistics','accounting','legal','devfactory',...
    name          text NOT NULL,
    description   text,
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE crm.products IS 'Справочник продаваемых продуктов/модулей FoxProFlow.';
COMMENT ON COLUMN crm.products.code IS 'Код продукта: logistics/accounting/legal/devfactory/...';

-- 4. Подписки (product + plan на аккаунте)
CREATE TABLE IF NOT EXISTS crm.subscriptions (
    id             bigserial PRIMARY KEY,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    account_id     bigint      NOT NULL REFERENCES crm.accounts(id),
    product_code   text        NOT NULL REFERENCES crm.products(code), -- FK на справочник продуктов
    plan_code      text        NOT NULL,        -- 'basic','pro','enterprise',...
    status         text        NOT NULL CHECK (
        status IN ('trial','active','suspended','cancelled')
    ),

    started_at     timestamptz,
    trial_ends_at  timestamptz,
    expires_at     timestamptz,

    currency       text,
    amount_month   numeric(14,2) CHECK (amount_month >= 0),
    billing_period text        NOT NULL DEFAULT 'monthly'
        CHECK (billing_period IN ('monthly','yearly')),
    payload        jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE crm.subscriptions IS 'Подписки аккаунтов на продукты/тарифы.';
COMMENT ON COLUMN crm.subscriptions.status IS 'trial/active/suspended/cancelled.';

CREATE INDEX IF NOT EXISTS idx_crm_subscriptions_account_status
    ON crm.subscriptions(account_id, status);

CREATE INDEX IF NOT EXISTS idx_crm_subscriptions_product_status
    ON crm.subscriptions(product_code, status);

-- Не даём завести две одновременные подписки (trial/active) на один продукт у одного аккаунта
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_subscriptions_account_product_active
    ON crm.subscriptions(account_id, product_code)
    WHERE status IN ('trial','active');

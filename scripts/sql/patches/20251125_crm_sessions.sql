-- 20251125_crm_sessions.sql
-- FoxProFlow — CRM: сессии продаж и онбординга.
-- NDC: только CREATE TABLE/INDEX IF NOT EXISTS,
--      никаких DROP/ALTER COLUMN/DELETE.

CREATE SCHEMA IF NOT EXISTS crm;

-- 1. Сессии продаж (чат/почта/звонок)
CREATE TABLE IF NOT EXISTS crm.sales_sessions (
    id            bigserial PRIMARY KEY,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    lead_id       bigint      REFERENCES crm.leads(id) ON DELETE CASCADE,
    channel       text        NOT NULL CHECK (
                     channel IN ('web_chat','email','partner_portal','manual')
                  ),                                  -- канал коммуникации
    status        text        NOT NULL CHECK (
                     status IN ('active','finished','aborted')
                  ),                                  -- статус сессии

    transcript    jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- массив сообщений
    summary       jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- резюме диалога
    last_event_id bigint                                   -- ops.event_log.id (логическая ссылка)
);

COMMENT ON TABLE crm.sales_sessions IS
'Сессии общения SalesFox с лидами (чат/почта/портал).';

COMMENT ON COLUMN crm.sales_sessions.channel IS
'Канал: web_chat/email/partner_portal/manual.';

COMMENT ON COLUMN crm.sales_sessions.status IS
'Статус: active (идёт диалог) / finished (закрыта) / aborted (прервана).';

CREATE INDEX IF NOT EXISTS idx_crm_sales_sessions_lead_created
    ON crm.sales_sessions(lead_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crm_sales_sessions_status
    ON crm.sales_sessions(status);

-- Не даём завести больше одной активной сессии по одному лиду
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_sales_sessions_lead_active
    ON crm.sales_sessions(lead_id)
    WHERE status = 'active';

-- 2. Сессии онбординга (цепочка шагов подключения)
CREATE TABLE IF NOT EXISTS crm.onboarding_sessions (
    id            bigserial PRIMARY KEY,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    account_id    bigint      REFERENCES crm.accounts(id) ON DELETE CASCADE,
    status        text        NOT NULL CHECK (
                     status IN ('pending','running','completed','failed')
                  ),

    steps         jsonb       NOT NULL DEFAULT '[]'::jsonb, -- шаги и статусы
    summary       jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE crm.onboarding_sessions IS
'Сессии онбординга (цепочки шагов подключения клиента).';

COMMENT ON COLUMN crm.onboarding_sessions.status IS
'Статус: pending (ожидает старта) / running (идёт онбординг) / '
'completed (успешно завершён) / failed (сорван).';

COMMENT ON COLUMN crm.onboarding_sessions.steps IS
'Шаги онбординга: массив объектов вида '
'[{step_code, status, started_at, finished_at, payload}, ...].';

CREATE INDEX IF NOT EXISTS idx_crm_onboarding_sessions_account_status
    ON crm.onboarding_sessions(account_id, status);

-- Не даём иметь две живые (pending/running) сессии онбординга на один аккаунт
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_onboarding_sessions_account_active
    ON crm.onboarding_sessions(account_id)
    WHERE status IN ( 'pending', 'running' );

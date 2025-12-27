-- scripts/sql/patches/20251207_flowmind_core_schema.sql
-- FlowMind v0.1 — базовая схема БД: планы, советы, снимки состояния.

BEGIN;

-- 0. Схема flowmind
CREATE SCHEMA IF NOT EXISTS flowmind;

-- 1. Планы FlowMind (flowmind.plan)
CREATE TABLE IF NOT EXISTS flowmind.plan (
    plan_id      uuid        PRIMARY KEY,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    status       text        NOT NULL, -- 'draft' | 'active' | 'completed' | 'cancelled'
    domain       text        NOT NULL, -- домен, к которому относится план (devfactory|logistics|crm|security|...)
    goal         text        NOT NULL,
    context      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    plan_json    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    meta         jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE flowmind.plan IS
'Планы FlowMind: цель, домен, шаги (plan_json) и контекст.';

-- 2. Советы FlowMind (flowmind.advice)
CREATE TABLE IF NOT EXISTS flowmind.advice (
    advice_id    uuid        PRIMARY KEY,
    created_at   timestamptz NOT NULL DEFAULT now(),
    plan_id      uuid        NULL,     -- опциональная ссылка на план FlowMind
    target_type  text        NOT NULL, -- 'devfactory_task' | 'devfactory_order' | 'tenant' | 'domain' | ...
    target_ref   text        NOT NULL, -- произвольный идентификатор цели (task_id, order_id, tenant_id и т.д.)
    severity     text        NOT NULL, -- 'info' | 'warning' | 'critical'
    status       text        NOT NULL, -- 'new' | 'ack' | 'dismissed'
    summary      text        NOT NULL,
    details      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    meta         jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE flowmind.advice IS
'Советы FlowMind по приоритизации и действиям над задачами/заказами/доменами.';

-- 3. Снимки состояния (flowmind.snapshot)
CREATE TABLE IF NOT EXISTS flowmind.snapshot (
    snapshot_id  uuid        PRIMARY KEY,
    created_at   timestamptz NOT NULL DEFAULT now(),
    source       text        NOT NULL, -- откуда сформирован снимок: 'devfactory-kpi', 'logistics-kpi', 'crm-kpi', ...
    summary      text        NULL,
    payload      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    meta         jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE flowmind.snapshot IS
'Снимки состояния организма, которые FlowMind использует для reasoning.';

-- Индексы
CREATE INDEX IF NOT EXISTS flowmind_plan_status_domain_idx
    ON flowmind.plan (status, domain, created_at);

CREATE INDEX IF NOT EXISTS flowmind_advice_target_idx
    ON flowmind.advice (target_type, target_ref, created_at);

CREATE INDEX IF NOT EXISTS flowmind_snapshot_created_idx
    ON flowmind.snapshot (created_at);

COMMIT;

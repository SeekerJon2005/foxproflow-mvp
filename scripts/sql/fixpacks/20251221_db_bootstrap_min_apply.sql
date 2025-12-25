-- FoxProFlow • DB bootstrap MIN (sec/dev/ops/planner) — recovery after empty pgdata
-- file: scripts/sql/fixpacks/20251221_db_bootstrap_min_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--  - Idempotent where possible (IF NOT EXISTS / CREATE OR REPLACE / ALTER ... IF NOT EXISTS)
--  - Goal: prevent API/worker/beat from crashing after Postgres volume loss
--  - Covers:
--      * FlowSec minimal: sec.roles, sec.subject_roles, sec.policies, sec.role_policy_bindings (+ seeds)
--      * DevFactory minimal: dev.dev_task (+ indexes)
--      * Ops event logging: ops.event_log (+ compat cols)
--      * Planner KPI: planner.kpi_snapshots + planner.kpi_snapshot() + planner.planner_kpi_daily (+ unique index)
-- Preconditions:
--  - Postgres 15+
-- Rollback:
--  - See D section in chat answer (DROP objects in reverse order).

\set ON_ERROR_STOP on
SET lock_timeout = '10s';
SET statement_timeout = '0';
SET client_min_messages = NOTICE;

-- =========================
-- SEC (FlowSec minimal)
-- =========================
CREATE SCHEMA IF NOT EXISTS sec;

CREATE TABLE IF NOT EXISTS sec.roles (
  id         bigserial PRIMARY KEY,
  role_code  text,
  code       text,
  name       text,
  is_active  boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Compat (if table existed with older shape)
ALTER TABLE IF EXISTS sec.roles ADD COLUMN IF NOT EXISTS role_code  text;
ALTER TABLE IF EXISTS sec.roles ADD COLUMN IF NOT EXISTS code       text;
ALTER TABLE IF EXISTS sec.roles ADD COLUMN IF NOT EXISTS name       text;
ALTER TABLE IF EXISTS sec.roles ADD COLUMN IF NOT EXISTS is_active  boolean;
ALTER TABLE IF EXISTS sec.roles ADD COLUMN IF NOT EXISTS created_at timestamptz;

ALTER TABLE IF EXISTS sec.roles ALTER COLUMN is_active  SET DEFAULT true;
ALTER TABLE IF EXISTS sec.roles ALTER COLUMN created_at SET DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS roles_role_code_uidx
  ON sec.roles(role_code) WHERE role_code IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS roles_code_uidx
  ON sec.roles(code) WHERE code IS NOT NULL;


CREATE TABLE IF NOT EXISTS sec.subject_roles (
  id           bigserial PRIMARY KEY,
  subject      text,
  subject_key  text,
  subject_id   text,          -- важно: text (email/opaque), НЕ uuid
  subject_type text,
  role         text,
  role_code    text,
  role_id      bigint,
  tenant_id    uuid,
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Compat columns
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS subject      text;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS subject_key  text;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS subject_id   text;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS subject_type text;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS role         text;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS role_code    text;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS role_id      bigint;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS tenant_id    uuid;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS is_active    boolean;
ALTER TABLE IF EXISTS sec.subject_roles ADD COLUMN IF NOT EXISTS created_at   timestamptz;

ALTER TABLE IF EXISTS sec.subject_roles ALTER COLUMN is_active  SET DEFAULT true;
ALTER TABLE IF EXISTS sec.subject_roles ALTER COLUMN created_at SET DEFAULT now();

CREATE INDEX IF NOT EXISTS subject_roles_subject_idx       ON sec.subject_roles(subject);
CREATE INDEX IF NOT EXISTS subject_roles_subject_id_idx    ON sec.subject_roles(subject_id);
CREATE INDEX IF NOT EXISTS subject_roles_subject_type_idx  ON sec.subject_roles(subject_type);
CREATE INDEX IF NOT EXISTS subject_roles_role_idx          ON sec.subject_roles(role);
CREATE INDEX IF NOT EXISTS subject_roles_role_code_idx     ON sec.subject_roles(role_code);
CREATE INDEX IF NOT EXISTS subject_roles_role_id_idx       ON sec.subject_roles(role_id);

CREATE UNIQUE INDEX IF NOT EXISTS subject_roles_uniq
  ON sec.subject_roles(subject_type, subject_id, role_code);


CREATE TABLE IF NOT EXISTS sec.policies (
  id            bigserial PRIMARY KEY,
  policy_code   text NOT NULL UNIQUE,
  effect        text NOT NULL DEFAULT 'allow',
  decision      text,
  domain        text NOT NULL,
  action        text,
  target_domain text,
  target_action text,
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS policies_domain_action_idx
  ON sec.policies(domain, action);

CREATE INDEX IF NOT EXISTS policies_target_domain_action_idx
  ON sec.policies(target_domain, target_action);


CREATE TABLE IF NOT EXISTS sec.role_policy_bindings (
  id          bigserial PRIMARY KEY,
  role_code   text NOT NULL,
  policy_code text NOT NULL,
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS role_policy_bindings_role_policy_uidx
  ON sec.role_policy_bindings(role_code, policy_code);

-- seeds (idempotent)
INSERT INTO sec.roles(role_code, code, name)
VALUES ('architect', 'architect', 'Architect')
ON CONFLICT DO NOTHING;

INSERT INTO sec.subject_roles(subject_type, subject_id, role_code, role, subject_key, subject)
VALUES ('user', 'e.yatskov@foxproflow.ru', 'architect', 'architect', 'e.yatskov@foxproflow.ru', 'e.yatskov@foxproflow.ru')
ON CONFLICT DO NOTHING;

INSERT INTO sec.policies(policy_code, effect, domain, action, decision, target_domain, target_action)
VALUES
  ('devfactory.view_tasks.allow',   'allow', 'devfactory', 'view_tasks',   'allow', 'devfactory', 'view_tasks'),
  ('devfactory.manage_tasks.allow', 'allow', 'devfactory', 'manage_tasks', 'allow', 'devfactory', 'manage_tasks')
ON CONFLICT (policy_code) DO NOTHING;

INSERT INTO sec.role_policy_bindings(role_code, policy_code)
VALUES
  ('architect', 'devfactory.view_tasks.allow'),
  ('architect', 'devfactory.manage_tasks.allow')
ON CONFLICT DO NOTHING;


-- =========================
-- OPS (event logging minimal)
-- =========================
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.event_log (
  id             bigserial PRIMARY KEY,
  ts             timestamptz NOT NULL DEFAULT now(),
  type           text,        -- legacy
  event_type     text,        -- new
  severity       text,
  tenant_id      uuid,
  correlation_id text,
  actor          text,
  message        text,
  payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
  ok             boolean,
  source         text,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- Compat columns (if table existed with drift)
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS ts             timestamptz;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS type           text;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS event_type     text;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS severity       text;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS tenant_id      uuid;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS correlation_id text;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS actor          text;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS message        text;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS payload        jsonb;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS ok             boolean;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS source         text;
ALTER TABLE IF EXISTS ops.event_log ADD COLUMN IF NOT EXISTS created_at     timestamptz;

ALTER TABLE IF EXISTS ops.event_log ALTER COLUMN ts         SET DEFAULT now();
ALTER TABLE IF EXISTS ops.event_log ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE IF EXISTS ops.event_log ALTER COLUMN payload    SET DEFAULT '{}'::jsonb;

-- Best-effort backfill: event_type from legacy type
DO $$
BEGIN
  IF to_regclass('ops.event_log') IS NOT NULL THEN
    EXECUTE $q$
      UPDATE ops.event_log
      SET event_type = COALESCE(event_type, type)
      WHERE event_type IS NULL AND type IS NOT NULL
    $q$;
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS event_log_ts_idx         ON ops.event_log (ts DESC);
CREATE INDEX IF NOT EXISTS event_log_event_type_idx ON ops.event_log (event_type);
CREATE INDEX IF NOT EXISTS event_log_type_idx       ON ops.event_log (type);
CREATE INDEX IF NOT EXISTS event_log_corr_idx       ON ops.event_log (correlation_id);


-- =========================
-- DEV (DevFactory minimal for gateway + intent)
-- =========================
CREATE SCHEMA IF NOT EXISTS dev;

CREATE TABLE IF NOT EXISTS dev.dev_task (
  id                 bigserial PRIMARY KEY,
  public_id           uuid,
  stack               text,
  title               text,
  status              text,
  source              text,
  input_spec          jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_spec         jsonb NOT NULL DEFAULT '{}'::jsonb,
  links               jsonb NOT NULL DEFAULT '{}'::jsonb,
  meta                jsonb NOT NULL DEFAULT '{}'::jsonb,
  error               text,
  autofix_enabled     boolean NOT NULL DEFAULT false,
  autofix_status      text    NOT NULL DEFAULT 'disabled',
  flowmind_plan_id     uuid,
  flowmind_plan_domain text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Compat columns (if table existed with smaller shape)
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS public_id           uuid;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS stack               text;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS title               text;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS status              text;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS source              text;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS input_spec          jsonb;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS result_spec         jsonb;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS links               jsonb;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS meta                jsonb;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS error               text;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS autofix_enabled     boolean;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS autofix_status      text;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS flowmind_plan_id     uuid;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS flowmind_plan_domain text;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS created_at          timestamptz;
ALTER TABLE IF EXISTS dev.dev_task ADD COLUMN IF NOT EXISTS updated_at          timestamptz;

ALTER TABLE IF EXISTS dev.dev_task ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE IF EXISTS dev.dev_task ALTER COLUMN updated_at SET DEFAULT now();

ALTER TABLE IF EXISTS dev.dev_task ALTER COLUMN input_spec  SET DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS dev.dev_task ALTER COLUMN result_spec SET DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS dev.dev_task ALTER COLUMN links       SET DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS dev.dev_task ALTER COLUMN meta        SET DEFAULT '{}'::jsonb;

-- Ensure NOT NULL where possible (best effort)
DO $$
BEGIN
  BEGIN
    ALTER TABLE dev.dev_task ALTER COLUMN input_spec SET NOT NULL;
  EXCEPTION WHEN others THEN NULL; END;
  BEGIN
    ALTER TABLE dev.dev_task ALTER COLUMN result_spec SET NOT NULL;
  EXCEPTION WHEN others THEN NULL; END;
  BEGIN
    ALTER TABLE dev.dev_task ALTER COLUMN links SET NOT NULL;
  EXCEPTION WHEN others THEN NULL; END;
  BEGIN
    ALTER TABLE dev.dev_task ALTER COLUMN meta SET NOT NULL;
  EXCEPTION WHEN others THEN NULL; END;
END
$$;

CREATE INDEX IF NOT EXISTS dev_task_status_idx     ON dev.dev_task(status);
CREATE INDEX IF NOT EXISTS dev_task_stack_idx      ON dev.dev_task(stack);
CREATE INDEX IF NOT EXISTS dev_task_created_at_idx ON dev.dev_task(created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS dev_task_public_id_uidx
  ON dev.dev_task(public_id) WHERE public_id IS NOT NULL;

-- Bump serial sequence if present (safe after manual inserts like id=324)
DO $$
DECLARE
  seq_text text;
BEGIN
  seq_text := pg_get_serial_sequence('dev.dev_task', 'id');
  IF seq_text IS NOT NULL THEN
    EXECUTE format(
      'SELECT setval(%L, (SELECT GREATEST(COALESCE(MAX(id),1),1) FROM dev.dev_task), true);',
      seq_text
    );
  END IF;
END
$$;


-- =========================
-- PLANNER (KPI snapshot)
-- =========================
CREATE SCHEMA IF NOT EXISTS planner;

CREATE TABLE IF NOT EXISTS planner.kpi_snapshots (
  id      bigserial PRIMARY KEY,
  ts      timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL
);

CREATE INDEX IF NOT EXISTS kpi_snapshots_ts_idx ON planner.kpi_snapshots(ts);

CREATE OR REPLACE FUNCTION planner.kpi_snapshot()
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  payload jsonb := '{}'::jsonb;
  counts  jsonb := '{}'::jsonb;
  t       text;
  cnt     bigint;
BEGIN
  payload := jsonb_build_object(
    'ts', now(),
    'db', current_database(),
    'server_version', current_setting('server_version', true)
  );

  FOREACH t IN ARRAY ARRAY[
    'dev.dev_task',
    'sec.subject_roles',
    'sec.roles',
    'sec.policies',
    'sec.role_policy_bindings',
    'planner.kpi_snapshots',
    'ops.event_log',
    'public.trips',
    'public.loads',
    'public.trip_segments',
    'public.vehicles'
  ]
  LOOP
    IF to_regclass(t) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %s', t) INTO cnt;
      counts := counts || jsonb_build_object(t, cnt);
    END IF;
  END LOOP;

  payload := payload || jsonb_build_object('counts', counts);

  INSERT INTO planner.kpi_snapshots(ts, payload)
  VALUES (now(), payload);
END;
$$;

DO $$
BEGIN
  IF to_regclass('planner.planner_kpi_daily') IS NULL THEN
    EXECUTE $mv$
      CREATE MATERIALIZED VIEW planner.planner_kpi_daily AS
      SELECT
        date_trunc('day', ts) AS day,
        count(*)              AS snapshots_cnt,
        max(ts)               AS last_ts
      FROM planner.kpi_snapshots
      GROUP BY 1
    $mv$;
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS planner_kpi_daily_day_uidx
  ON planner.planner_kpi_daily(day);

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

\echo '=== OK: db_bootstrap_min_apply finished ==='

-- file: scripts/sql/fixpacks/20251222_db_bootstrap_min_apply.sql
-- FoxProFlow • FixPack • DB BOOTSTRAP MIN (public/sec/dev/ops/planner)
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Минимальный скелет БД, чтобы стенд не падал после потери volume:
--     - PUBLIC meta stubs (alembic_version / schema_migrations)
--     - FlowSec MIN (таблицы + базовые политики)
--     - DevFactory MIN (dev.dev_task + schema-align: source/error/links/meta + id default)
--     - ops event logging MIN (ops.event_log + correlation_id)
--     - planner KPI MIN (snapshots + callable + daily matview)
-- Idempotent. Не делает DROP. Best-effort на потенциально конфликтных индексах.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858371);

-- =========================
-- SCHEMAS
-- =========================
CREATE SCHEMA IF NOT EXISTS sec;
CREATE SCHEMA IF NOT EXISTS dev;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS planner;

-- =========================
-- PUBLIC META (migration stubs)
-- =========================
CREATE TABLE IF NOT EXISTS public.alembic_version (
  version_num varchar(32) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS public.schema_migrations (
  version text PRIMARY KEY
);

-- =========================
-- SEC (FlowSec minimal)
-- =========================
CREATE TABLE IF NOT EXISTS sec.roles (
  id         bigserial PRIMARY KEY,
  role_code  text,
  code       text,
  name       text,
  is_active  boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- unique indexes: best-effort (не валим bootstrap, если в старой базе дубли)
DO $$
BEGIN
  BEGIN
    EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS roles_role_code_uidx ON sec.roles(role_code) WHERE role_code IS NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'sec.roles role_code unique index skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS roles_code_uidx ON sec.roles(code) WHERE code IS NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'sec.roles code unique index skipped: %', SQLERRM;
  END;
END$$;

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
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS subject_roles_subject_key_idx   ON sec.subject_roles(subject_key);
CREATE INDEX IF NOT EXISTS subject_roles_subject_idx       ON sec.subject_roles(subject);
CREATE INDEX IF NOT EXISTS subject_roles_subject_id_idx    ON sec.subject_roles(subject_id);
CREATE INDEX IF NOT EXISTS subject_roles_subject_type_idx  ON sec.subject_roles(subject_type);
CREATE INDEX IF NOT EXISTS subject_roles_role_idx          ON sec.subject_roles(role);
CREATE INDEX IF NOT EXISTS subject_roles_role_code_idx     ON sec.subject_roles(role_code);
CREATE INDEX IF NOT EXISTS subject_roles_role_id_idx       ON sec.subject_roles(role_id);

-- best-effort unique (чтобы не упасть на дублях)
DO $$
BEGIN
  BEGIN
    EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS subject_roles_uniq ON sec.subject_roles(subject_type, subject_id, role_code)
             WHERE subject_type IS NOT NULL AND subject_id IS NOT NULL AND role_code IS NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'sec.subject_roles unique index skipped: %', SQLERRM;
  END;
END$$;

-- Best-effort align: если subject_id был uuid в старой базе — приводим к text
DO $$
DECLARE
  udt text;
BEGIN
  IF to_regclass('sec.subject_roles') IS NULL THEN
    RETURN;
  END IF;

  SELECT c.udt_name INTO udt
  FROM information_schema.columns c
  WHERE c.table_schema='sec' AND c.table_name='subject_roles' AND c.column_name='subject_id';

  IF udt = 'uuid' THEN
    BEGIN
      EXECUTE 'ALTER TABLE sec.subject_roles ALTER COLUMN subject_id TYPE text USING subject_id::text';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'sec.subject_roles.subject_id type align skipped: %', SQLERRM;
    END;
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS sec.policies (
  id            bigserial PRIMARY KEY,
  policy_code   text,
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

-- unique on policy_code: best-effort
DO $$
BEGIN
  BEGIN
    EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS policies_policy_code_uidx ON sec.policies(policy_code) WHERE policy_code IS NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'sec.policies policy_code unique index skipped: %', SQLERRM;
  END;
END$$;

CREATE TABLE IF NOT EXISTS sec.role_policy_bindings (
  id          bigserial PRIMARY KEY,
  role_code   text NOT NULL,
  policy_code text NOT NULL,
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- best-effort unique
DO $$
BEGIN
  BEGIN
    EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS role_policy_bindings_role_policy_uidx
             ON sec.role_policy_bindings(role_code, policy_code)';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'sec.role_policy_bindings unique index skipped: %', SQLERRM;
  END;
END$$;

-- SEC seeds (минимум для DevFactory)
INSERT INTO sec.roles(role_code, code, name)
SELECT 'architect', 'architect', 'Architect'
WHERE NOT EXISTS (
  SELECT 1 FROM sec.roles WHERE role_code='architect' OR code='architect'
);

INSERT INTO sec.policies(policy_code, effect, domain, action, decision, target_domain, target_action)
SELECT 'devfactory.view_tasks.allow', 'allow', 'devfactory', 'view_tasks', 'allow', 'devfactory', 'view_tasks'
WHERE NOT EXISTS (SELECT 1 FROM sec.policies WHERE policy_code='devfactory.view_tasks.allow');

INSERT INTO sec.policies(policy_code, effect, domain, action, decision, target_domain, target_action)
SELECT 'devfactory.manage_tasks.allow', 'allow', 'devfactory', 'manage_tasks', 'allow', 'devfactory', 'manage_tasks'
WHERE NOT EXISTS (SELECT 1 FROM sec.policies WHERE policy_code='devfactory.manage_tasks.allow');

INSERT INTO sec.role_policy_bindings(role_code, policy_code)
SELECT 'architect', 'devfactory.view_tasks.allow'
WHERE NOT EXISTS (
  SELECT 1 FROM sec.role_policy_bindings WHERE role_code='architect' AND policy_code='devfactory.view_tasks.allow'
);

INSERT INTO sec.role_policy_bindings(role_code, policy_code)
SELECT 'architect', 'devfactory.manage_tasks.allow'
WHERE NOT EXISTS (
  SELECT 1 FROM sec.role_policy_bindings WHERE role_code='architect' AND policy_code='devfactory.manage_tasks.allow'
);

-- =========================
-- DEV (DevFactory minimal for gateway) + schema align
-- =========================
CREATE TABLE IF NOT EXISTS dev.dev_task (
  id          bigserial PRIMARY KEY,
  public_id   uuid,
  stack       text,
  title       text,
  status      text,
  source      text,
  project_ref text,
  language    text,
  channel     text,
  input_spec  jsonb,
  result_spec jsonb,
  links       jsonb,
  meta        jsonb,
  error       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS dev_task_status_idx       ON dev.dev_task(status);
CREATE INDEX IF NOT EXISTS dev_task_stack_idx        ON dev.dev_task(stack);
CREATE INDEX IF NOT EXISTS dev_task_project_ref_idx  ON dev.dev_task(project_ref);

-- public_id часто используется как внешний ключ/ссылка; делаем уникальность только если не NULL
DO $$
BEGIN
  IF to_regclass('dev.dev_task') IS NOT NULL THEN
    BEGIN
      EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS dev_task_public_id_uidx
               ON dev.dev_task(public_id) WHERE public_id IS NOT NULL';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'dev.dev_task public_id unique index skipped: %', SQLERRM;
    END;
  END IF;
END$$;

-- Align existing dev.dev_task to expected minimal columns + ensure id default exists
DO $$
DECLARE
  has_default boolean;
  max_id bigint;
BEGIN
  IF to_regclass('dev.dev_task') IS NULL THEN
    RETURN;
  END IF;

  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS public_id   uuid;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS stack       text;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS title       text;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS status      text;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS source      text;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS project_ref text;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS language    text;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS channel     text;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS input_spec  jsonb;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS result_spec jsonb;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS links       jsonb;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS meta        jsonb;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS error       text;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS created_at  timestamptz;
  ALTER TABLE dev.dev_task ADD COLUMN IF NOT EXISTS updated_at  timestamptz;

  BEGIN
    ALTER TABLE dev.dev_task ALTER COLUMN created_at SET DEFAULT now();
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'dev.dev_task created_at default skipped: %', SQLERRM;
  END;

  BEGIN
    ALTER TABLE dev.dev_task ALTER COLUMN updated_at SET DEFAULT now();
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'dev.dev_task updated_at default skipped: %', SQLERRM;
  END;

  BEGIN
    ALTER TABLE dev.dev_task ALTER COLUMN meta SET DEFAULT '{}'::jsonb;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'dev.dev_task meta default skipped: %', SQLERRM;
  END;

  -- ensure PK exists (best-effort)
  BEGIN
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conrelid='dev.dev_task'::regclass AND contype='p'
    ) THEN
      EXECUTE 'ALTER TABLE dev.dev_task ADD CONSTRAINT dev_task_pkey PRIMARY KEY (id)';
    END IF;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'dev.dev_task primary key ensure skipped: %', SQLERRM;
  END;

  -- ensure id default exists (на случай “id без default”)
  SELECT (pg_get_expr(ad.adbin, ad.adrelid) IS NOT NULL) INTO has_default
  FROM pg_attribute a
  LEFT JOIN pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum
  WHERE a.attrelid='dev.dev_task'::regclass AND a.attname='id' AND NOT a.attisdropped;

  IF NOT has_default THEN
    EXECUTE 'CREATE SEQUENCE IF NOT EXISTS dev.dev_task_id_seq';
    EXECUTE 'ALTER TABLE dev.dev_task ALTER COLUMN id SET DEFAULT nextval(''dev.dev_task_id_seq'')';
    EXECUTE 'SELECT COALESCE(max(id),0) FROM dev.dev_task' INTO max_id;
    PERFORM setval('dev.dev_task_id_seq', GREATEST(max_id+1, 1), false);
  END IF;
END$$;

-- =========================
-- OPS (event logging minimal) + correlation_id
-- =========================
CREATE TABLE IF NOT EXISTS ops.event_log (
  id             bigserial PRIMARY KEY,
  ts             timestamptz NOT NULL DEFAULT now(),
  created_at     timestamptz NOT NULL DEFAULT now(),
  correlation_id text,
  event_type     text,
  type           text,
  source         text,
  severity       text,
  ok             boolean,
  message        text,
  error          text,
  project_ref    text,
  language       text,
  channel        text,
  links          jsonb,
  payload        jsonb,
  context        jsonb
);

CREATE INDEX IF NOT EXISTS event_log_ts_idx
  ON ops.event_log(ts);

CREATE INDEX IF NOT EXISTS event_log_source_ts_idx
  ON ops.event_log(source, ts DESC);

CREATE INDEX IF NOT EXISTS ops_event_log_correlation_id_idx
  ON ops.event_log(correlation_id);

-- совместимость: если таблица уже была, но без части колонок/дефолтов
DO $$
DECLARE
  max_id bigint;
  has_default boolean;
BEGIN
  IF to_regclass('ops.event_log') IS NULL THEN
    RETURN;
  END IF;

  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS ts             timestamptz;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS created_at     timestamptz;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS correlation_id text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS event_type     text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS type           text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS source         text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS severity       text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS ok             boolean;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS message        text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS error          text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS project_ref    text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS language       text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS channel        text;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS links          jsonb;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS payload        jsonb;
  ALTER TABLE ops.event_log ADD COLUMN IF NOT EXISTS context        jsonb;

  BEGIN
    ALTER TABLE ops.event_log ALTER COLUMN ts         SET DEFAULT now();
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ops.event_log ts default skipped: %', SQLERRM;
  END;

  BEGIN
    ALTER TABLE ops.event_log ALTER COLUMN created_at SET DEFAULT now();
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ops.event_log created_at default skipped: %', SQLERRM;
  END;

  -- ensure id default exists (на случай “id без default”)
  SELECT (pg_get_expr(ad.adbin, ad.adrelid) IS NOT NULL) INTO has_default
  FROM pg_attribute a
  LEFT JOIN pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum
  WHERE a.attrelid='ops.event_log'::regclass AND a.attname='id' AND NOT a.attisdropped;

  IF NOT has_default THEN
    EXECUTE 'CREATE SEQUENCE IF NOT EXISTS ops.event_log_id_seq';
    EXECUTE 'ALTER TABLE ops.event_log ALTER COLUMN id SET DEFAULT nextval(''ops.event_log_id_seq'')';
    EXECUTE 'SELECT COALESCE(max(id),0) FROM ops.event_log' INTO max_id;
    PERFORM setval('ops.event_log_id_seq', GREATEST(max_id+1, 1), false);
  END IF;
END$$;

-- =========================
-- PLANNER (KPI snapshot)
-- =========================
CREATE TABLE IF NOT EXISTS planner.kpi_snapshots (
  id      bigserial PRIMARY KEY,
  ts      timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL
);

CREATE INDEX IF NOT EXISTS kpi_snapshots_ts_idx
  ON planner.kpi_snapshots(ts);

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
    BEGIN
      IF to_regclass(t) IS NOT NULL THEN
        EXECUTE format('SELECT count(*) FROM %s', t) INTO cnt;
        counts := counts || jsonb_build_object(t, cnt);
      END IF;
    EXCEPTION WHEN OTHERS THEN
      counts := counts || jsonb_build_object(t, NULL);
    END;
  END LOOP;

  payload := payload || jsonb_build_object('counts', counts);

  INSERT INTO planner.kpi_snapshots(ts, payload)
  VALUES (now(), payload);
END
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

-- =========================
-- ANALYZE (cheap, helps plans)
-- =========================
ANALYZE public.alembic_version;
ANALYZE public.schema_migrations;

ANALYZE sec.roles;
ANALYZE sec.subject_roles;
ANALYZE sec.policies;
ANALYZE sec.role_policy_bindings;

ANALYZE dev.dev_task;

ANALYZE ops.event_log;

ANALYZE planner.kpi_snapshots;

SELECT pg_advisory_unlock(74858371);

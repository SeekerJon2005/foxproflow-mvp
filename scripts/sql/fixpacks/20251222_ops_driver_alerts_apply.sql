-- file: scripts/sql/fixpacks/20251222_ops_driver_alerts_apply.sql
-- FoxProFlow • FixPack • ops.driver_alerts bootstrap (for driver.alerts.offroute + dispatcher alerts storage)
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Source (ported + aligned to code contract):
--   - B-dev/scripts/sql/patches/20251125_driver_alerts.sql
--   - B-dev/scripts/sql/patches/20251126_ops_driver_alerts_resolve.sql
-- Contract (from code):
--   - src/worker/tasks_driver_alerts.py (INSERT + fresh-check)
--   - src/api/routers/dispatcher_alerts.py (SELECT/UPDATE/RETURNING)
-- Requirements:
--   - ops.driver_alerts table (NOT view)
--   - id bigserial PK; ts default now(); trip_id uuid NOT NULL; driver_id text NULL;
--   - alert_type/level/message NOT NULL; details jsonb NOT NULL; resolved_* nullable
--   - indexes: ts DESC; (trip_id, alert_type, ts DESC); optional driver_id ts; optional partial resolved_at IS NULL
-- Idempotent. No DROP. Best-effort aligns existing tables without breaking bootstrap.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858375);

CREATE SCHEMA IF NOT EXISTS ops;

-- =========================================================
-- 1) Create table (fresh DB) with the CURRENT contract
-- =========================================================
CREATE TABLE IF NOT EXISTS ops.driver_alerts (
    id               bigserial PRIMARY KEY,
    ts               timestamptz NOT NULL DEFAULT now(),
    trip_id           uuid        NOT NULL,
    driver_id         text        NULL,
    alert_type        text        NOT NULL,  -- off_route, eta_delay, speed, ...
    level             text        NOT NULL,  -- info, warn, critical
    message           text        NOT NULL,
    details           jsonb       NOT NULL DEFAULT '{}'::jsonb,
    resolved_at       timestamptz NULL,
    resolved_by       text        NULL,
    resolved_comment  text        NULL
);

-- =========================================================
-- 2) Comments (safe even if re-run)
-- =========================================================
COMMENT ON TABLE ops.driver_alerts IS
    'События/алерты по поведению водителя (off-route, задержки по ETA и др.).';

COMMENT ON COLUMN ops.driver_alerts.id IS
    'Технический идентификатор алерта (bigserial).';

COMMENT ON COLUMN ops.driver_alerts.ts IS
    'Время возникновения/фиксации алерта.';

COMMENT ON COLUMN ops.driver_alerts.trip_id IS
    'Рейс, к которому относится алерт.';

COMMENT ON COLUMN ops.driver_alerts.driver_id IS
    'Водитель (идентификатор/opaque), допускается NULL.';

COMMENT ON COLUMN ops.driver_alerts.alert_type IS
    'Тип алерта (off_route, eta_delay, speed_limit и т.п.).';

COMMENT ON COLUMN ops.driver_alerts.level IS
    'Уровень важности (info, warn, critical).';

COMMENT ON COLUMN ops.driver_alerts.message IS
    'Краткое человекочитаемое описание алерта (NOT NULL).';

COMMENT ON COLUMN ops.driver_alerts.details IS
    'Структурированные параметры алерта (расстояния, detour_factor, ETA и т.п.), jsonb NOT NULL.';

COMMENT ON COLUMN ops.driver_alerts.resolved_at IS 'Когда алерт закрыт диспетчером';
COMMENT ON COLUMN ops.driver_alerts.resolved_by IS 'Кем закрыт (логин/имя)';
COMMENT ON COLUMN ops.driver_alerts.resolved_comment IS 'Комментарий диспетчера';

-- =========================================================
-- 3) Schema-align existing DB (best-effort, do not fail bootstrap)
-- =========================================================
DO $$
DECLARE
  udt_driver_id text;
BEGIN
  IF to_regclass('ops.driver_alerts') IS NULL THEN
    RETURN;
  END IF;

  -- Add missing columns (if table existed in some older shape)
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS ts              timestamptz;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS trip_id         uuid;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS driver_id       text;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS alert_type      text;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS level           text;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS message         text;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS details         jsonb;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS resolved_at     timestamptz;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS resolved_by     text;
  ALTER TABLE ops.driver_alerts ADD COLUMN IF NOT EXISTS resolved_comment text;

  -- Ensure defaults (best-effort)
  BEGIN
    EXECUTE 'ALTER TABLE ops.driver_alerts ALTER COLUMN ts SET DEFAULT now()';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ops.driver_alerts ts default skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'ALTER TABLE ops.driver_alerts ALTER COLUMN details SET DEFAULT ''{}''::jsonb';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ops.driver_alerts details default skipped: %', SQLERRM;
  END;

  -- Align driver_id type: uuid -> text if needed
  SELECT c.udt_name INTO udt_driver_id
  FROM information_schema.columns c
  WHERE c.table_schema='ops' AND c.table_name='driver_alerts' AND c.column_name='driver_id';

  IF udt_driver_id = 'uuid' THEN
    BEGIN
      EXECUTE 'ALTER TABLE ops.driver_alerts ALTER COLUMN driver_id TYPE text USING driver_id::text';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'ops.driver_alerts driver_id type align skipped: %', SQLERRM;
    END;
  END IF;

  -- Enforce message NOT NULL (safe: fill NULL first)
  BEGIN
    EXECUTE 'UPDATE ops.driver_alerts SET message = '''' WHERE message IS NULL';
    EXECUTE 'ALTER TABLE ops.driver_alerts ALTER COLUMN message SET DEFAULT ''''';
    EXECUTE 'ALTER TABLE ops.driver_alerts ALTER COLUMN message SET NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ops.driver_alerts message NOT NULL align skipped: %', SQLERRM;
  END;

  -- Enforce details NOT NULL (safe: fill NULL first)
  BEGIN
    EXECUTE 'UPDATE ops.driver_alerts SET details = ''{}''::jsonb WHERE details IS NULL';
    EXECUTE 'ALTER TABLE ops.driver_alerts ALTER COLUMN details SET NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ops.driver_alerts details NOT NULL align skipped: %', SQLERRM;
  END;

END$$;

-- =========================================================
-- 4) Indexes (minimum for current queries; keep legacy ones too)
-- =========================================================

-- Latest alerts w/o filters
CREATE INDEX IF NOT EXISTS idx_driver_alerts_ts_desc
    ON ops.driver_alerts (ts DESC);

-- Legacy-ish: trip -> last alerts
CREATE INDEX IF NOT EXISTS idx_driver_alerts_trip_ts
    ON ops.driver_alerts (trip_id, ts DESC);

-- Fresh-check for offroute: trip + type + recent ts (core for driver.alerts.offroute)
CREATE INDEX IF NOT EXISTS idx_driver_alerts_trip_type_ts
    ON ops.driver_alerts (trip_id, alert_type, ts DESC);

-- Optional: driver timeline (works for dispatcher list too)
CREATE INDEX IF NOT EXISTS idx_driver_alerts_driver_ts
    ON ops.driver_alerts (driver_id, ts DESC);

-- Optional: type timeline
CREATE INDEX IF NOT EXISTS idx_driver_alerts_type_ts
    ON ops.driver_alerts (alert_type, ts DESC);

-- Optional: fast path for "open" alerts (unresolved)
CREATE INDEX IF NOT EXISTS idx_driver_alerts_open_trip_type_ts
    ON ops.driver_alerts (trip_id, alert_type, ts DESC)
    WHERE resolved_at IS NULL;

ANALYZE ops.driver_alerts;

SELECT pg_advisory_unlock(74858375);

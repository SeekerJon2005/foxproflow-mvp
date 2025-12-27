-- FoxProFlow • FixPack • DriverId support for driver.offroute (telemetry + assignments)
-- file: scripts/sql/fixpacks/20251223_driver_id_support_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Remove skipped_no_driver + prevent SQL errors in driver.offroute by providing driver_id sources:
--     1) public.driver_telemetry.driver_id (optional, direct)
--     2) public.driver_assignments (fallback mapping by tractor/truck/vehicle/trip, with started_at window)
-- Notes:
--   tasks_driver_alerts.py references:
--     - da.tractor_id
--     - da.started_at (<= now())
--   so we must provide these columns.
-- Idempotent. No DROP.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858382);

CREATE SCHEMA IF NOT EXISTS public;

-- 1) Telemetry: add driver_id if missing
DO $$
BEGIN
  IF to_regclass('public.driver_telemetry') IS NOT NULL THEN
    ALTER TABLE public.driver_telemetry
      ADD COLUMN IF NOT EXISTS driver_id text;

    CREATE INDEX IF NOT EXISTS driver_telemetry_driver_ts_idx
      ON public.driver_telemetry (driver_id, ts DESC)
      WHERE driver_id IS NOT NULL;
  END IF;
END$$;

-- 2) Assignments: minimal table for resolving driver_id by tractor/truck/vehicle/trip + started_at window
CREATE TABLE IF NOT EXISTS public.driver_assignments (
  id         bigserial PRIMARY KEY,
  ts         timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  truck_id    bigint NULL,
  tractor_id  text   NULL, -- referenced by codepaths (da.tractor_id)
  vehicle_id  bigint NULL,
  trip_id     bigint NULL,

  -- time window referenced by codepaths (da.started_at <= now())
  started_at  timestamptz NOT NULL DEFAULT now(),
  ended_at    timestamptz NULL,

  driver_id  text   NOT NULL,
  is_active  boolean NOT NULL DEFAULT true,

  source     text NULL,
  meta       jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- schema-align (in case table existed in different shape)
DO $$
BEGIN
  IF to_regclass('public.driver_assignments') IS NULL THEN
    RETURN;
  END IF;

  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS ts         timestamptz;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS created_at timestamptz;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS updated_at timestamptz;

  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS truck_id    bigint;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS tractor_id  text;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS vehicle_id  bigint;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS trip_id     bigint;

  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS started_at  timestamptz;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS ended_at    timestamptz;

  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS driver_id  text;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS is_active  boolean;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS source     text;
  ALTER TABLE public.driver_assignments ADD COLUMN IF NOT EXISTS meta       jsonb;

  -- defaults / not-null best-effort
  BEGIN
    EXECUTE 'ALTER TABLE public.driver_assignments ALTER COLUMN meta SET DEFAULT ''{}''::jsonb';
    EXECUTE 'UPDATE public.driver_assignments SET meta=''{}''::jsonb WHERE meta IS NULL';
    EXECUTE 'ALTER TABLE public.driver_assignments ALTER COLUMN meta SET NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'driver_assignments meta align skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'ALTER TABLE public.driver_assignments ALTER COLUMN ts SET DEFAULT now()';
    EXECUTE 'ALTER TABLE public.driver_assignments ALTER COLUMN created_at SET DEFAULT now()';
    EXECUTE 'ALTER TABLE public.driver_assignments ALTER COLUMN updated_at SET DEFAULT now()';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'driver_assignments ts defaults skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'ALTER TABLE public.driver_assignments ALTER COLUMN started_at SET DEFAULT now()';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'driver_assignments started_at default skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'ALTER TABLE public.driver_assignments ALTER COLUMN is_active SET DEFAULT true';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'driver_assignments is_active default skipped: %', SQLERRM;
  END;
END$$;

-- Backfill: tractor_id from truck_id (best-effort)
DO $$
BEGIN
  IF to_regclass('public.driver_assignments') IS NOT NULL THEN
    BEGIN
      EXECUTE 'UPDATE public.driver_assignments
               SET tractor_id = truck_id::text
               WHERE tractor_id IS NULL AND truck_id IS NOT NULL';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'driver_assignments tractor_id backfill skipped: %', SQLERRM;
    END;
  END IF;
END$$;

-- Backfill: started_at (so da.started_at <= now() filters work)
DO $$
BEGIN
  IF to_regclass('public.driver_assignments') IS NOT NULL THEN
    BEGIN
      EXECUTE 'UPDATE public.driver_assignments
               SET started_at = COALESCE(started_at, created_at, ts, now())
               WHERE started_at IS NULL';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'driver_assignments started_at backfill skipped: %', SQLERRM;
    END;

    -- best-effort set NOT NULL if possible
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM public.driver_assignments WHERE started_at IS NULL) THEN
        EXECUTE 'ALTER TABLE public.driver_assignments ALTER COLUMN started_at SET NOT NULL';
      END IF;
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'driver_assignments started_at NOT NULL skipped: %', SQLERRM;
    END;
  END IF;
END$$;

-- Indexes (support "latest assignment" lookups)
CREATE INDEX IF NOT EXISTS driver_assignments_truck_created_idx
  ON public.driver_assignments (truck_id, created_at DESC)
  WHERE truck_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS driver_assignments_vehicle_created_idx
  ON public.driver_assignments (vehicle_id, created_at DESC)
  WHERE vehicle_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS driver_assignments_trip_created_idx
  ON public.driver_assignments (trip_id, created_at DESC)
  WHERE trip_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS driver_assignments_active_truck_idx
  ON public.driver_assignments (is_active, truck_id)
  WHERE truck_id IS NOT NULL;

-- Tractor indexes (because code queries da.tractor_id and normalizes it)
CREATE INDEX IF NOT EXISTS driver_assignments_tractor_created_idx
  ON public.driver_assignments (tractor_id, created_at DESC)
  WHERE tractor_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS driver_assignments_active_tractor_idx
  ON public.driver_assignments (is_active, tractor_id)
  WHERE tractor_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS driver_assignments_tractor_norm_idx
  ON public.driver_assignments ((lower(trim(both from tractor_id))))
  WHERE tractor_id IS NOT NULL;

-- Time-window helper (started_at <= now() typical filter)
CREATE INDEX IF NOT EXISTS driver_assignments_tractor_started_idx
  ON public.driver_assignments (tractor_id, started_at DESC)
  WHERE tractor_id IS NOT NULL;

ANALYZE public.driver_telemetry;
ANALYZE public.driver_assignments;

SELECT pg_advisory_unlock(74858382);

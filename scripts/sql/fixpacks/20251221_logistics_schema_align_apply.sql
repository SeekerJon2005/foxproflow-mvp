-- FoxProFlow • FixPack • Logistics schema align (Schema Doctor)
-- file: scripts/sql/fixpacks/20251221_logistics_schema_align_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Close runtime gaps found in worker logs:
--     - public.driver_telemetry missing -> driver.alerts.offroute skips/crash-loop
--     - public.trips.truck_id missing (legacy expected by some offroute query paths)
--     - public.driver_telemetry.truck_id optional legacy mirror (truck_id vs vehicle_id)
-- Non-destructive: only CREATE IF NOT EXISTS / ALTER ADD COLUMN IF NOT EXISTS / safe UPDATE.
-- Idempotent. No DROP.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858374);

-- public schema defensive create
CREATE SCHEMA IF NOT EXISTS public;

-- =========================================================
-- 1) driver telemetry (needed by driver.alerts.offroute query)
-- =========================================================
CREATE TABLE IF NOT EXISTS public.driver_telemetry (
    id          bigserial PRIMARY KEY,
    ts          timestamptz NOT NULL DEFAULT now(),

    vehicle_id  bigint NULL,
    truck_id    bigint NULL,  -- legacy mirror of vehicle_id when needed
    trip_id     bigint NULL,  -- legacy/internal id (if used)

    lat         double precision NULL,
    lon         double precision NULL,

    speed_kmh   numeric(10,2) NULL,
    heading_deg numeric(10,2) NULL,
    odo_km      numeric(12,3) NULL,

    source      text NULL,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Schema-align existing table (if it existed in older shape)
DO $$
BEGIN
  IF to_regclass('public.driver_telemetry') IS NULL THEN
    RETURN;
  END IF;

  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS ts          timestamptz;
  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS vehicle_id  bigint;
  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS truck_id    bigint;
  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS trip_id     bigint;

  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS lat         double precision;
  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS lon         double precision;

  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS speed_kmh   numeric(10,2);
  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS heading_deg numeric(10,2);
  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS odo_km      numeric(12,3);

  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS source      text;
  ALTER TABLE public.driver_telemetry ADD COLUMN IF NOT EXISTS payload     jsonb;

  -- defaults / not-null (best-effort)
  BEGIN
    EXECUTE 'ALTER TABLE public.driver_telemetry ALTER COLUMN ts SET DEFAULT now()';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'driver_telemetry ts default skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'ALTER TABLE public.driver_telemetry ALTER COLUMN payload SET DEFAULT ''{}''::jsonb';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'driver_telemetry payload default skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'UPDATE public.driver_telemetry SET payload = ''{}''::jsonb WHERE payload IS NULL';
    EXECUTE 'ALTER TABLE public.driver_telemetry ALTER COLUMN payload SET NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'driver_telemetry payload NOT NULL align skipped: %', SQLERRM;
  END;
END
$$;

-- Indexes for telemetry access patterns
CREATE INDEX IF NOT EXISTS driver_telemetry_ts_idx
    ON public.driver_telemetry (ts);

CREATE INDEX IF NOT EXISTS driver_telemetry_trip_ts_idx
    ON public.driver_telemetry (trip_id, ts DESC)
    WHERE trip_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS driver_telemetry_vehicle_ts_idx
    ON public.driver_telemetry (vehicle_id, ts DESC)
    WHERE vehicle_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS driver_telemetry_truck_ts_idx
    ON public.driver_telemetry (truck_id, ts DESC)
    WHERE truck_id IS NOT NULL;

-- Best-effort backfill: truck_id from vehicle_id (legacy mirror)
DO $$
BEGIN
  IF to_regclass('public.driver_telemetry') IS NOT NULL THEN
    BEGIN
      EXECUTE 'UPDATE public.driver_telemetry
               SET truck_id = vehicle_id
               WHERE truck_id IS NULL AND vehicle_id IS NOT NULL';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'driver_telemetry truck_id backfill skipped: %', SQLERRM;
    END;
  END IF;
END
$$;

-- =========================================================
-- 2) Legacy compatibility: trips.truck_id
--    Keep both: vehicle_id (canonical) + truck_id (legacy mirror).
-- =========================================================
DO $$
BEGIN
  IF to_regclass('public.trips') IS NOT NULL THEN
    BEGIN
      EXECUTE 'ALTER TABLE public.trips ADD COLUMN IF NOT EXISTS truck_id bigint';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'public.trips truck_id add skipped: %', SQLERRM;
    END;

    BEGIN
      EXECUTE 'UPDATE public.trips
               SET truck_id = vehicle_id
               WHERE truck_id IS NULL AND vehicle_id IS NOT NULL';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'public.trips truck_id backfill skipped: %', SQLERRM;
    END;

    BEGIN
      EXECUTE 'CREATE INDEX IF NOT EXISTS trips_truck_id_idx ON public.trips(truck_id)';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'public.trips trips_truck_id_idx create skipped: %', SQLERRM;
    END;
  END IF;
END
$$;

-- =========================================================
-- ANALYZE
-- =========================================================
ANALYZE public.driver_telemetry;

DO $$
BEGIN
  IF to_regclass('public.trips') IS NOT NULL THEN
    EXECUTE 'ANALYZE public.trips';
  END IF;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'ANALYZE public.trips skipped: %', SQLERRM;
END
$$;

SELECT pg_advisory_unlock(74858374);

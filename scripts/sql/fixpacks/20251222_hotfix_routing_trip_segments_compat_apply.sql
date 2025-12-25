-- file: scripts/sql/fixpacks/20251222_hotfix_routing_trip_segments_compat_apply.sql
-- FoxProFlow • FixPack • Hotfix: routing.enrich.trips compat columns
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Ensure columns required by /app/src/worker/tasks/routing.py exist:
--     - public.trip_segments: trip_id, segment_order, origin/dest, coords, road_km/drive_sec, polylines
--     - public.trips: created_at, confirmed_at
-- Idempotent. Does not DROP.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';

SELECT pg_advisory_lock(74858373);

DO $$
DECLARE
  trips_id_type text;
  trip_segments_has_trip_id boolean;
BEGIN
  IF to_regclass('public.trips') IS NULL THEN
    RAISE NOTICE 'public.trips is missing; skip routing compat patch';
    RETURN;
  END IF;

  IF to_regclass('public.trip_segments') IS NULL THEN
    RAISE NOTICE 'public.trip_segments is missing; skip routing compat patch';
    RETURN;
  END IF;

  -- Determine exact SQL type of public.trips.id
  SELECT format_type(a.atttypid, a.atttypmod)
    INTO trips_id_type
  FROM pg_attribute a
  JOIN pg_class c ON c.oid = a.attrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname='public' AND c.relname='trips' AND a.attname='id'
    AND a.attnum > 0 AND NOT a.attisdropped;

  IF trips_id_type IS NULL THEN
    RAISE NOTICE 'Cannot determine type of public.trips.id; trip_segments.trip_id will NOT be added';
  ELSE
    SELECT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema='public' AND table_name='trip_segments' AND column_name='trip_id'
    ) INTO trip_segments_has_trip_id;

    IF NOT trip_segments_has_trip_id THEN
      EXECUTE format('ALTER TABLE public.trip_segments ADD COLUMN trip_id %s', trips_id_type);
    END IF;
  END IF;

  -- public.trips columns used in routing.py ORDER BY
  ALTER TABLE public.trips ADD COLUMN IF NOT EXISTS created_at  timestamptz NOT NULL DEFAULT now();
  ALTER TABLE public.trips ADD COLUMN IF NOT EXISTS confirmed_at timestamptz;

  -- public.trip_segments columns used in routing.py SELECT/WHERE/ORDER/UPDATE
  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS segment_order integer;
  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS origin_region text;
  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS dest_region   text;

  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS src_lat double precision;
  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS src_lon double precision;
  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS dst_lat double precision;
  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS dst_lon double precision;

  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS road_km  numeric;
  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS drive_sec integer;

  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS route_polyline text;
  ALTER TABLE public.trip_segments ADD COLUMN IF NOT EXISTS polyline       text;

END$$;

-- Indexes (safe/idempotent)
DO $$
BEGIN
  IF to_regclass('public.trip_segments') IS NOT NULL THEN
    -- only if trip_id exists
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name='trip_segments' AND column_name='trip_id'
    ) THEN
      CREATE INDEX IF NOT EXISTS trip_segments_trip_id_idx
        ON public.trip_segments(trip_id);

      CREATE INDEX IF NOT EXISTS trip_segments_trip_id_segord_idx
        ON public.trip_segments(trip_id, segment_order);
    END IF;
  END IF;

  IF to_regclass('public.trips') IS NOT NULL THEN
    CREATE INDEX IF NOT EXISTS trips_created_at_idx
      ON public.trips(created_at);

    CREATE INDEX IF NOT EXISTS trips_confirmed_at_idx
      ON public.trips(confirmed_at);
  END IF;
END$$;

ANALYZE public.trips;
ANALYZE public.trip_segments;

SELECT pg_advisory_unlock(74858373);

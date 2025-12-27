-- FoxProFlow • FixPack • BOOTSTRAP MIN (CP1)
-- file: scripts/sql/fixpacks/20251221_bootstrap_min_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
--
-- Adds:
--   - loading_region/unloading_region to trips/trip_segments/loads
--   - trip_segments: segment_order, road_km, drive_sec, polyline
--   - trips: confirmed_at
--   - supportive indexes
--
-- Idempotent + one-writer via advisory lock

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';

SELECT pg_advisory_lock(74858371);

-- Preflight: base tables must exist
DO $$
BEGIN
  IF to_regclass('public.trips') IS NULL
     OR to_regclass('public.trip_segments') IS NULL
     OR to_regclass('public.loads') IS NULL
  THEN
    RAISE EXCEPTION
      'BOOTSTRAP MIN blocked: base tables missing in db=% (expected public.trips/public.trip_segments/public.loads).',
      current_database();
  END IF;
END$$;

-- A) Regions
ALTER TABLE public.trips
  ADD COLUMN IF NOT EXISTS loading_region text,
  ADD COLUMN IF NOT EXISTS unloading_region text;

ALTER TABLE public.trip_segments
  ADD COLUMN IF NOT EXISTS loading_region text,
  ADD COLUMN IF NOT EXISTS unloading_region text;

ALTER TABLE public.loads
  ADD COLUMN IF NOT EXISTS loading_region text,
  ADD COLUMN IF NOT EXISTS unloading_region text;

-- Indexes (online)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_trips_loading_region
  ON public.trips (loading_region);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_trips_unloading_region
  ON public.trips (unloading_region);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_trip_segments_loading_region
  ON public.trip_segments (loading_region);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_trip_segments_unloading_region
  ON public.trip_segments (unloading_region);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_loads_loading_region
  ON public.loads (loading_region);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_loads_unloading_region
  ON public.loads (unloading_region);

-- B) Routing metrics + segment ordering
ALTER TABLE public.trip_segments
  ADD COLUMN IF NOT EXISTS segment_order integer,
  ADD COLUMN IF NOT EXISTS road_km numeric,
  ADD COLUMN IF NOT EXISTS drive_sec integer,
  ADD COLUMN IF NOT EXISTS polyline text;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_trip_segments_trip_id_segment_order
  ON public.trip_segments (trip_id, segment_order);

-- C) Confirm timestamp
ALTER TABLE public.trips
  ADD COLUMN IF NOT EXISTS confirmed_at timestamptz;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_trips_confirmed_at
  ON public.trips (confirmed_at);

ANALYZE public.trips;
ANALYZE public.trip_segments;
ANALYZE public.loads;

SELECT pg_advisory_unlock(74858371);

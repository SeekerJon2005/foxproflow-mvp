-- FoxProFlow • FixPack • 2025-12-26
-- file: scripts/sql/fixpacks/20251226_trip_segments_region_cols_compat_apply.sql
-- Purpose:
--   Ensure public.trip_segments contains columns required by
--   scripts/sql/fixpacks/20251221_booking_windows_and_availability_apply.sql
--   for creating public.vehicle_availability_mv on a fresh database:
--     - unloading_region
--     - dest_city
--
-- Idempotent / safe to re-run.

\pset pager off
\set ON_ERROR_STOP on

SET lock_timeout = '5s';
SET statement_timeout = '0';

SELECT pg_advisory_lock(hashtext('ff:fixpack:20251226:trip_segments_region_cols')::bigint);

DO $$
BEGIN
  IF to_regclass('public.trip_segments') IS NULL THEN
    RAISE EXCEPTION 'MISSING: public.trip_segments (apply logistics bootstrap first)';
  END IF;
END $$;

ALTER TABLE public.trip_segments
  ADD COLUMN IF NOT EXISTS unloading_region text;

ALTER TABLE public.trip_segments
  ADD COLUMN IF NOT EXISTS dest_city text;

COMMENT ON COLUMN public.trip_segments.unloading_region IS
  'Compat: region name for unloading (required by public.vehicle_availability_mv bootstrap).';

COMMENT ON COLUMN public.trip_segments.dest_city IS
  'Compat: destination city (required by public.vehicle_availability_mv bootstrap).';

ANALYZE public.trip_segments;

SELECT pg_advisory_unlock(hashtext('ff:fixpack:20251226:trip_segments_region_cols')::bigint) AS unlocked;

\echo OK: ensured public.trip_segments region columns (unloading_region, dest_city)

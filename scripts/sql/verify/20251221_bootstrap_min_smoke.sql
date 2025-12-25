-- FoxProFlow • Verify/Smoke • BOOTSTRAP MIN
-- file: scripts/sql/verify/20251221_bootstrap_min_smoke.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--   READ-ONLY checks. Safe to run multiple times.

\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

-- Objects exist
SELECT
  to_regclass('public.trips')        AS public_trips,
  to_regclass('public.trip_segments') AS public_trip_segments,
  to_regclass('public.loads')        AS public_loads;

-- Required columns: trips
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='public' AND table_name='trips'
  AND column_name IN ('loading_region','unloading_region','confirmed_at')
ORDER BY column_name;

-- Required columns: trip_segments
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='public' AND table_name='trip_segments'
  AND column_name IN ('loading_region','unloading_region','segment_order','road_km','drive_sec','polyline')
ORDER BY column_name;

-- Required columns: loads
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='public' AND table_name='loads'
  AND column_name IN ('loading_region','unloading_region')
ORDER BY column_name;

-- Index presence (best-effort visibility)
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname='public'
  AND (
    indexname IN (
      'ix_trips_loading_region',
      'ix_trips_unloading_region',
      'ix_trip_segments_loading_region',
      'ix_trip_segments_unloading_region',
      'ix_loads_loading_region',
      'ix_loads_unloading_region',
      'ix_trip_segments_trip_id_segment_order',
      'ix_trips_confirmed_at'
    )
  )
ORDER BY 1,2,3;

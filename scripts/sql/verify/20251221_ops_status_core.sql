-- FoxProFlow • OPS/Verify • Core DB status
-- file: scripts/sql/verify/20251221_ops_status_core.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
--
-- Purpose:
--   One-shot SQL dashboard for CP1 data layer readiness.
--
-- Notes:
--   - READ-ONLY
--   - Safe to run repeatedly
--   - Fail-fast if key objects missing

\set ON_ERROR_STOP on
\pset pager off

-- ---------------------------------------------------------------------------
-- Header / context
-- ---------------------------------------------------------------------------
SELECT
  now() AS ts_now,
  current_database() AS db,
  current_user AS db_user,
  current_setting('TimeZone', true) AS timezone,
  version() AS pg_version;

-- ---------------------------------------------------------------------------
-- Extensions (required for gen_random_uuid etc.)
-- ---------------------------------------------------------------------------
SELECT extname, extversion
FROM pg_extension
WHERE extname IN ('pgcrypto')
ORDER BY extname;

-- ---------------------------------------------------------------------------
-- 0) Preconditions (fail-fast)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF to_regclass('public.vehicles') IS NULL THEN
    RAISE EXCEPTION 'Missing table: public.vehicles';
  END IF;
  IF to_regclass('public.loads') IS NULL THEN
    RAISE EXCEPTION 'Missing table: public.loads';
  END IF;
  IF to_regclass('public.trips') IS NULL THEN
    RAISE EXCEPTION 'Missing table: public.trips';
  END IF;
  IF to_regclass('public.trip_segments') IS NULL THEN
    RAISE EXCEPTION 'Missing table: public.trip_segments';
  END IF;

  IF to_regclass('public.vehicle_availability_mv') IS NULL THEN
    RAISE EXCEPTION 'Missing MV: public.vehicle_availability_mv';
  END IF;
  IF to_regclass('public.v_window_sla_violations') IS NULL THEN
    RAISE EXCEPTION 'Missing view: public.v_window_sla_violations';
  END IF;
END$$;

-- ---------------------------------------------------------------------------
-- READY gate (structure-only readiness)
--   READY means: core objects exist + required unique MV index exists.
--   Data may still be empty (valid for fresh bootstrap).
-- ---------------------------------------------------------------------------
WITH req AS (
  SELECT
    to_regclass('public.vehicle_availability_mv') IS NOT NULL AS mv_ok,
    to_regclass('public.v_window_sla_violations') IS NOT NULL AS view_ok,
    EXISTS (
      SELECT 1
      FROM pg_indexes
      WHERE schemaname='public'
        AND tablename='vehicle_availability_mv'
        AND indexname='ux_vehicle_availability_mv_vehicle_id'
    ) AS mv_unique_idx_ok
)
SELECT
  CASE WHEN mv_ok AND view_ok AND mv_unique_idx_ok THEN 'READY' ELSE 'NOT_READY' END AS cp1_data_layer_status,
  mv_ok, view_ok, mv_unique_idx_ok
FROM req;

-- ---------------------------------------------------------------------------
-- 1) Core table row counts
-- ---------------------------------------------------------------------------
SELECT 'vehicles'::text AS tbl, count(*)::bigint AS rows FROM public.vehicles
UNION ALL SELECT 'loads', count(*) FROM public.loads
UNION ALL SELECT 'trips', count(*) FROM public.trips
UNION ALL SELECT 'trip_segments', count(*) FROM public.trip_segments
ORDER BY tbl;

-- ---------------------------------------------------------------------------
-- 2) MV freshness
-- ---------------------------------------------------------------------------
SELECT
  (SELECT count(*) FROM public.vehicle_availability_mv) AS mv_rows,
  (SELECT max(computed_at) FROM public.vehicle_availability_mv) AS mv_max_computed_at;

-- ---------------------------------------------------------------------------
-- Data change vs MV freshness (staleness)
--   updated_at exists on all core tables in current schema.
-- ---------------------------------------------------------------------------
WITH
last_changes AS (
  SELECT max(updated_at) AS last_updated_at FROM public.vehicles
  UNION ALL SELECT max(updated_at) FROM public.loads
  UNION ALL SELECT max(updated_at) FROM public.trips
  UNION ALL SELECT max(updated_at) FROM public.trip_segments
),
core_last_updated AS (
  SELECT max(last_updated_at) AS core_last_updated_at
  FROM last_changes
),
mv AS (
  SELECT max(computed_at) AS mv_max_computed_at
  FROM public.vehicle_availability_mv
)
SELECT
  c.core_last_updated_at,
  m.mv_max_computed_at,
  CASE
    WHEN c.core_last_updated_at IS NULL THEN 'NO_DATA'
    WHEN m.mv_max_computed_at IS NULL THEN 'MV_EMPTY'
    WHEN m.mv_max_computed_at >= c.core_last_updated_at THEN 'FRESH'
    ELSE 'STALE'
  END AS mv_staleness_status,
  CASE
    WHEN c.core_last_updated_at IS NULL OR m.mv_max_computed_at IS NULL THEN NULL::interval
    ELSE (c.core_last_updated_at - m.mv_max_computed_at)
  END AS mv_lag
FROM core_last_updated c
CROSS JOIN mv m;

-- ---------------------------------------------------------------------------
-- 3) SLA violations (top)
-- ---------------------------------------------------------------------------
SELECT scope, violation, count(*) AS cnt
FROM public.v_window_sla_violations
GROUP BY 1,2
ORDER BY cnt DESC, scope, violation
LIMIT 20;

-- ---------------------------------------------------------------------------
-- 4) Key objects exist (sanity)
-- ---------------------------------------------------------------------------
SELECT
  to_regclass('public.vehicle_availability_mv') AS vehicle_availability_mv,
  to_regclass('public.v_window_sla_violations') AS v_window_sla_violations;

-- ---------------------------------------------------------------------------
-- 5) Key indexes exist (sanity)
-- ---------------------------------------------------------------------------
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname='public'
  AND (
    (tablename='vehicle_availability_mv' AND indexname IN (
      'ux_vehicle_availability_mv_vehicle_id',
      'ix_vehicle_availability_mv_region_available',
      'ix_vehicle_availability_mv_available_only',
      'ix_vehicle_availability_mv_available_from',
      'ix_vehicle_availability_mv_last_unloading_region'
    ))
    OR
    (tablename IN ('loads','trip_segments','trips') AND indexname IN (
      'loads_load_window_start_idx',
      'loads_unload_window_start_idx',
      'loads_status_idx',
      'trip_segments_planned_load_start_idx',
      'trip_segments_planned_unload_end_idx',
      'trip_segments_trip_seq_uidx',
      'ix_trips_confirmed_at',
      'ix_trip_segments_trip_id_segment_order'
    ))
  )
ORDER BY tablename, indexname;

-- ---------------------------------------------------------------------------
-- 6) Constraints presence (informational; NOT VALID is expected for CP1)
-- ---------------------------------------------------------------------------
SELECT
  conrelid::regclass AS rel,
  conname,
  convalidated
FROM pg_constraint
WHERE conrelid IN ('public.loads'::regclass, 'public.trip_segments'::regclass)
  AND conname IN (
    'loads_load_window_order_chk',
    'loads_unload_window_order_chk',
    'trip_segments_planned_load_order_chk',
    'trip_segments_planned_unload_order_chk'
  )
ORDER BY conrelid::regclass::text, conname;

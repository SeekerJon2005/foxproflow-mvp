-- FoxProFlow • Smoke • Booking Windows + Vehicle Availability MV
-- file: scripts/sql/verify/20251221_booking_windows_and_availability_smoke.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

-- Objects exist
SELECT
  to_regclass('public.v_window_sla_violations') AS v_window_sla_violations,
  to_regclass('public.vehicle_availability_mv') AS vehicle_availability_mv;

-- Constraints exist
SELECT conname
FROM pg_constraint
WHERE conrelid IN ('public.loads'::regclass, 'public.trip_segments'::regclass)
  AND conname IN (
    'loads_load_window_order_chk',
    'loads_unload_window_order_chk',
    'trip_segments_planned_load_order_chk',
    'trip_segments_planned_unload_order_chk'
  )
ORDER BY 1;

-- MV has required unique non-partial index for CONCURRENT refresh
WITH m AS (
  SELECT c.oid AS relid
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname='public' AND c.relname='vehicle_availability_mv'
),
idx AS (
  SELECT
    i.relname AS indexname,
    ix.indisunique,
    ix.indisvalid,
    (ix.indpred IS NOT NULL) AS is_partial
  FROM m
  JOIN pg_index ix ON ix.indrelid = m.relid
  JOIN pg_class i ON i.oid = ix.indexrelid
)
SELECT
  bool_or(indisunique AND indisvalid AND NOT is_partial) AS has_unique_nonpartial,
  string_agg(
    CASE WHEN indisunique THEN indexname || CASE WHEN is_partial THEN ' (partial)' ELSE '' END ELSE NULL END,
    ', ' ORDER BY indexname
  ) FILTER (WHERE indisunique) AS unique_indexes
FROM idx;

-- Sample rows
SELECT vehicle_id, available_from_calc, last_unloading_region, computed_at
FROM public.vehicle_availability_mv
ORDER BY vehicle_id
LIMIT 10;

-- Zero/low violations is expected; but this is informational
SELECT scope, violation, count(*) AS cnt
FROM public.v_window_sla_violations
GROUP BY 1,2
ORDER BY cnt DESC, scope, violation;

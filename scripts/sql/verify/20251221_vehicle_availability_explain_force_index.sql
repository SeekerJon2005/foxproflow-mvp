-- FoxProFlow • Verify • EXPLAIN with seqscan disabled (diagnostic)
-- file: scripts/sql/verify/20251221_vehicle_availability_explain_force_index.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
--
-- NOTE:
--   This is diagnostic only. It forces planner to consider indexes.

\set ON_ERROR_STOP on
\pset pager off

SET enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT vehicle_id, available_from_calc, last_unloading_region
FROM public.vehicle_availability_mv
WHERE last_unloading_region = 'DebugDestRegion'
  AND available_from_calc <= now() + interval '2 days'
ORDER BY available_from_calc
LIMIT 10;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT vehicle_id, available_from_calc
FROM public.vehicle_availability_mv
WHERE available_from_calc <= now() + interval '2 days'
ORDER BY available_from_calc
LIMIT 10;

RESET enable_seqscan;

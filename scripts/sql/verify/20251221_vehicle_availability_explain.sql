-- FoxProFlow • Verify • EXPLAIN for vehicle availability queries
-- file: scripts/sql/verify/20251221_vehicle_availability_explain.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

-- Scenario A: region + available_from cutoff
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT vehicle_id, available_from_calc, last_unloading_region
FROM public.vehicle_availability_mv
WHERE last_unloading_region = 'DebugDestRegion'
  AND available_from_calc <= now() + interval '2 days'
ORDER BY available_from_calc
LIMIT 10;

-- Scenario B: only time cutoff (top-N)
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT vehicle_id, available_from_calc
FROM public.vehicle_availability_mv
WHERE available_from_calc <= now() + interval '2 days'
ORDER BY available_from_calc
LIMIT 10;

-- FoxProFlow • FixPack • vehicle_availability_mv indexes for planner
-- file: scripts/sql/fixpacks/20251221_vehicle_availability_indexes_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '10min';

SELECT pg_advisory_lock(74858371);

DO $$
BEGIN
  IF to_regclass('public.vehicle_availability_mv') IS NULL THEN
    RAISE EXCEPTION 'vehicle_availability_mv does not exist';
  END IF;
END$$;

-- For queries like: WHERE available_from_calc <= $ts AND last_unloading_region = $r
CREATE INDEX IF NOT EXISTS ix_vehicle_availability_mv_region_available
  ON public.vehicle_availability_mv (last_unloading_region, available_from_calc);

-- For queries like: WHERE last_unloading_region = $r ORDER BY available_from_calc LIMIT N
-- (covered by the same index above)

-- For queries like: WHERE available_from_calc <= $ts ORDER BY available_from_calc LIMIT N
CREATE INDEX IF NOT EXISTS ix_vehicle_availability_mv_available_only
  ON public.vehicle_availability_mv (available_from_calc);

ANALYZE public.vehicle_availability_mv;

SELECT pg_advisory_unlock(74858371);

-- FoxProFlow • OPS • Refresh vehicle_availability_mv
-- file: scripts/sql/ops/refresh_vehicle_availability_mv.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
--
-- Purpose:
--   Safe refresh routine for vehicle_availability_mv
--   - use CONCURRENTLY when possible
--   - fall back to non-concurrent if needed (but still fail-fast by default)

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '10min';

-- precheck
DO $$
BEGIN
  IF to_regclass('public.vehicle_availability_mv') IS NULL THEN
    RAISE EXCEPTION 'vehicle_availability_mv does not exist';
  END IF;
END$$;

-- CONCURRENT refresh requires unique non-partial valid index (we have it)
REFRESH MATERIALIZED VIEW CONCURRENTLY public.vehicle_availability_mv;

ANALYZE public.vehicle_availability_mv;

SELECT now() AS refreshed_at;

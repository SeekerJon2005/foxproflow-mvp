-- FoxProFlow • Smoke • vehicle_availability_mv indexes
-- file: scripts/sql/verify/20251221_vehicle_availability_indexes_smoke.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SELECT to_regclass('public.vehicle_availability_mv') AS vehicle_availability_mv;

SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname='public'
  AND tablename='vehicle_availability_mv'
  AND indexname IN (
    'ux_vehicle_availability_mv_vehicle_id',
    'ix_vehicle_availability_mv_available_from',
    'ix_vehicle_availability_mv_last_unloading_region',
    'ix_vehicle_availability_mv_region_available',
    'ix_vehicle_availability_mv_available_only'
  )
ORDER BY indexname;

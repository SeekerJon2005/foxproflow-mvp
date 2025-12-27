-- FoxProFlow • Verify/Smoke • driver_id support (telemetry + assignments)
-- file: scripts/sql/verify/20251223_driver_id_support_smoke.sql
\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

SELECT
  coalesce(to_regclass('public.driver_telemetry')::text,'MISSING') AS driver_telemetry,
  coalesce(to_regclass('public.driver_assignments')::text,'MISSING') AS driver_assignments;

-- telemetry has driver_id?
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='public' AND table_name='driver_telemetry'
  AND column_name='driver_id';

-- assignments required columns (incl tractor_id + started_at)
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='public' AND table_name='driver_assignments'
  AND column_name IN ('tractor_id','truck_id','vehicle_id','trip_id','driver_id','is_active','started_at','ended_at','created_at','ts')
ORDER BY column_name;

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname='public' AND tablename IN ('driver_telemetry','driver_assignments')
ORDER BY tablename, indexname;

-- FoxProFlow • Verify/Smoke • ops.driver_alerts.trip_id type align
-- file: scripts/sql/verify/20251223_ops_driver_alerts_trip_id_align_smoke.sql
\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

SELECT
  (SELECT udt_name FROM information_schema.columns
   WHERE table_schema='public' AND table_name='trips' AND column_name='id') AS trips_id_udt,
  (SELECT udt_name FROM information_schema.columns
   WHERE table_schema='ops' AND table_name='driver_alerts' AND column_name='trip_id') AS alerts_trip_id_udt,
  (SELECT count(*) FROM ops.driver_alerts) AS driver_alerts_rows;

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname='ops' AND tablename='driver_alerts'
ORDER BY indexname;

-- FoxProFlow • Verify/Smoke • ops.driver_alerts fill driver_id trigger/backfill
-- file: scripts/sql/verify/20251223_ops_driver_alerts_fill_driver_id_smoke.sql
\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

SELECT coalesce(to_regclass('ops.driver_alerts')::text,'MISSING') AS driver_alerts;

-- trigger present?
SELECT tgname
FROM pg_trigger
WHERE tgrelid='ops.driver_alerts'::regclass
  AND tgname='t_driver_alerts_fill_driver_id'
  AND NOT tgisinternal;

-- how many alerts still without driver_id?
SELECT
  count(*) AS alerts_total,
  count(*) FILTER (WHERE driver_id IS NULL OR length(trim(driver_id))=0) AS alerts_driver_missing
FROM ops.driver_alerts;

-- last alerts
SELECT id, ts, trip_id, driver_id,
       details->>'driver_src' AS driver_src,
       level, left(message,120) AS message
FROM ops.driver_alerts
ORDER BY ts DESC
LIMIT 10;

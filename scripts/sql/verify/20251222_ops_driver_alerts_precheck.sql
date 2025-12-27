-- file: scripts/sql/verify/20251222_ops_driver_alerts_precheck.sql
-- FoxProFlow • Verify • ops.driver_alerts presence + DoD probe
-- Created by: Архитектор Яцков Евгений Анатольевич
\set ON_ERROR_STOP on
\pset pager off

SELECT
  now() AS ts_now,
  current_database() AS db,
  current_user AS db_user,
  version() AS pg_version;

-- 1) presence
SELECT coalesce(to_regclass('ops.driver_alerts')::text,'MISSING') AS ops_driver_alerts;

-- 2) if exists: show columns (0 rows if missing, безопасно)
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='ops' AND table_name='driver_alerts'
ORDER BY ordinal_position;

-- 3) DoD probe via last task stats (работает даже если таблицы нет)
SELECT
  ts,
  payload->>'reason' AS reason,
  (payload->'stats'->>'skipped_missing_ops_driver_alerts')::int AS skipped_missing_ops_driver_alerts,
  (payload->'stats'->>'inserted_warn')::int AS inserted_warn,
  (payload->'stats'->>'inserted_critical')::int AS inserted_critical,
  (payload->'stats'->>'scanned_trips')::int AS scanned_trips
FROM ops.event_log
WHERE source='driver.offroute' AND event_type='done'
ORDER BY ts DESC
LIMIT 10;

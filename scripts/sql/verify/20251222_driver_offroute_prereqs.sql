-- file: scripts/sql/verify/20251222_driver_offroute_prereqs.sql
-- FoxProFlow • Verify • driver.offroute prerequisites (data readiness)
\set ON_ERROR_STOP on
\pset pager off

SELECT
  now() AS ts_now,
  current_database() AS db,
  current_user AS db_user;

SELECT
  coalesce(to_regclass('public.trips')::text,'MISSING')           AS trips,
  coalesce(to_regclass('public.driver_telemetry')::text,'MISSING') AS driver_telemetry,
  coalesce(to_regclass('ops.driver_alerts')::text,'MISSING')       AS driver_alerts;

-- core counts
SELECT count(*) AS trips_cnt FROM public.trips;

SELECT
  count(*) FILTER (WHERE status='confirmed') AS trips_confirmed_cnt,
  count(*) FILTER (WHERE status='confirmed' AND truck_id IS NOT NULL) AS trips_confirmed_with_truck_cnt
FROM public.trips;

SELECT
  count(*) AS telemetry_cnt,
  max(ts)  AS telemetry_last_ts
FROM public.driver_telemetry;

-- trips that would be joinable by the current code path (telemetry_window_mins=10080 default)
SELECT
  count(*) AS trips_with_recent_telemetry
FROM public.trips t
WHERE t.status='confirmed'
  AND t.truck_id IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM public.driver_telemetry dt
    WHERE dt.trip_id::text = t.id::text
      AND dt.ts > now() - make_interval(mins => 10080)
  );

-- last offroute runs (reason evolution)
SELECT ts,
       payload->>'reason' AS reason,
       (payload->'stats'->>'scanned_trips')::int AS scanned_trips,
       (payload->'stats'->>'skipped_missing_driver_telemetry')::int AS skipped_missing_driver_telemetry,
       (payload->'stats'->>'skipped_no_telemetry')::int AS skipped_no_telemetry
FROM ops.event_log
WHERE source='driver.offroute' AND event_type='done'
ORDER BY ts DESC
LIMIT 10;

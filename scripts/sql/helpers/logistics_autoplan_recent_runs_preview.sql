-- logistics_autoplan_recent_runs_preview.sql
-- DevTask: 92
-- Создал Архитектор: Яцков Евгений Анатольевич
-- Требует: применён патч scripts/sql/patches/20251212_logistics_autoplan_engine_v0_2.sql
-- FIX: window -> plan_window (и алиасим в "window" только как заголовок вывода)

\set ON_ERROR_STOP on

\echo ''
\echo '--- Recent autoplan runs (last 10) ---'
SELECT
  run_id,
  created_at,
  requested_date,
  plan_window AS "window",
  ok,
  loads_considered,
  vehicles_count,
  assignments_count,
  delayed_assignments,
  avg_start_delay_min
FROM logistics.autoplan_run
ORDER BY created_at DESC
LIMIT 10;

\echo ''
\echo '--- Latest run: header ---'
WITH last_run AS (
  SELECT *
  FROM logistics.autoplan_run
  ORDER BY created_at DESC
  LIMIT 1
)
SELECT
  run_id,
  created_at,
  requested_date,
  plan_window AS "window",
  window_start,
  window_end,
  ok,
  loads_considered,
  vehicles_count,
  assignments_count,
  delayed_assignments,
  avg_start_delay_min,
  error,
  payload
FROM last_run;

\echo ''
\echo '--- Latest run: assignments by vehicle (counts / max delay) ---'
WITH last_run AS (
  SELECT run_id
  FROM logistics.autoplan_run
  ORDER BY created_at DESC
  LIMIT 1
)
SELECT
  a.vehicle_code,
  COUNT(*) AS assignments_cnt,
  SUM(CASE WHEN a.start_delay_min > 0 THEN 1 ELSE 0 END) AS delayed_cnt,
  MAX(a.start_delay_min) AS max_start_delay_min
FROM logistics.autoplan_assignment a
JOIN last_run lr ON lr.run_id = a.run_id
GROUP BY a.vehicle_code
ORDER BY assignments_cnt DESC, a.vehicle_code
LIMIT 50;

\echo ''
\echo '--- Latest run: first 50 assignments (ordered) ---'
WITH last_run AS (
  SELECT run_id
  FROM logistics.autoplan_run
  ORDER BY created_at DESC
  LIMIT 1
)
SELECT
  a.vehicle_code,
  a.seq,
  a.load_id,
  a.planned_pickup_at,
  a.planned_delivery_at,
  a.start_delay_min,
  a.note
FROM logistics.autoplan_assignment a
JOIN last_run lr ON lr.run_id = a.run_id
ORDER BY a.vehicle_code, a.seq
LIMIT 50;

\echo ''
\echo '--- Latest run: top delayed assignments (start_delay_min desc) ---'
WITH last_run AS (
  SELECT run_id
  FROM logistics.autoplan_run
  ORDER BY created_at DESC
  LIMIT 1
)
SELECT
  a.vehicle_code,
  a.seq,
  a.load_id,
  a.planned_pickup_at,
  a.planned_delivery_at,
  a.start_delay_min,
  a.note
FROM logistics.autoplan_assignment a
JOIN last_run lr ON lr.run_id = a.run_id
WHERE a.start_delay_min > 0
ORDER BY a.start_delay_min DESC, a.vehicle_code, a.seq
LIMIT 20;

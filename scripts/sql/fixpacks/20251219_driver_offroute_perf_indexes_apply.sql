-- FoxProFlow • LANE-C • Perf indexes for driver_offroute_scan (no Python changes)
-- file: scripts/sql/fixpacks/20251219_driver_offroute_perf_indexes_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--  - Idempotent + schema-adaptive: picks real columns via information_schema.
--  - Safe: CREATE INDEX CONCURRENTLY IF NOT EXISTS.
-- Preconditions:
--  - Postgres 15+
-- Rollback:
--  - DROP INDEX CONCURRENTLY IF EXISTS <index_name>;

\set ON_ERROR_STOP on
SET lock_timeout = '10s';

-- ========= A) ops.driver_alerts indexes (key + time DESC) =========
WITH cols AS (
  SELECT column_name
  FROM information_schema.columns
  WHERE table_schema='ops' AND table_name='driver_alerts'
),
pick AS (
  SELECT
    (SELECT name FROM (VALUES
      ('created_at'),
      ('ts'),
      ('event_ts'),
      ('alert_ts'),
      ('occurred_at'),
      ('inserted_at')
    ) v(name)
     WHERE EXISTS (SELECT 1 FROM cols WHERE column_name=v.name)
     ORDER BY
       CASE name
         WHEN 'created_at' THEN 1
         WHEN 'ts' THEN 2
         WHEN 'event_ts' THEN 3
         WHEN 'alert_ts' THEN 4
         WHEN 'occurred_at' THEN 5
         ELSE 6
       END
     LIMIT 1) AS time_col
),
keys AS (
  SELECT name AS key_col
  FROM (VALUES
    ('trip_id'),
    ('driver_id'),
    ('tractor_id'),
    ('truck_id'),
    ('vehicle_id')
  ) v(name)
  WHERE EXISTS (SELECT 1 FROM cols WHERE column_name=v.name)
),
pairs AS (
  SELECT k.key_col, p.time_col
  FROM keys k CROSS JOIN pick p
  WHERE to_regclass('ops.driver_alerts') IS NOT NULL
    AND p.time_col IS NOT NULL
)
SELECT format(
  'CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON ops.driver_alerts (%I, %I DESC);',
  'ix_ops_driver_alerts_'||key_col||'_'||time_col||'_desc',
  key_col, time_col
) AS ddl
FROM pairs;
\gexec

SELECT 'ANALYZE ops.driver_alerts;' WHERE to_regclass('ops.driver_alerts') IS NOT NULL;
\gexec

-- ========= B) public.driver_telemetry index (id + time DESC) =========
WITH cols AS (
  SELECT column_name
  FROM information_schema.columns
  WHERE table_schema='public' AND table_name='driver_telemetry'
),
pick AS (
  SELECT
    (SELECT name FROM (VALUES
      ('tractor_id'),
      ('truck_id'),
      ('vehicle_id'),
      ('tractor_key'),
      ('truck_key'),
      ('vehicle_key'),
      ('tractor_id_txt'),
      ('truck_id_txt'),
      ('vehicle_id_txt')
    ) v(name)
     WHERE EXISTS (SELECT 1 FROM cols WHERE column_name=v.name)
     ORDER BY
       CASE name
         WHEN 'tractor_id' THEN 1
         WHEN 'truck_id' THEN 2
         WHEN 'vehicle_id' THEN 3
         WHEN 'tractor_key' THEN 4
         WHEN 'truck_key' THEN 5
         WHEN 'vehicle_key' THEN 6
         WHEN 'tractor_id_txt' THEN 7
         WHEN 'truck_id_txt' THEN 8
         ELSE 9
       END
     LIMIT 1) AS id_col,

    (SELECT name FROM (VALUES
      ('ts'),
      ('ts_utc'),
      ('event_ts'),
      ('gps_ts'),
      ('fix_ts'),
      ('event_time'),
      ('gps_time'),
      ('created_at'),
      ('created_ts'),
      ('received_at'),
      ('inserted_at'),
      ('tstamp')
    ) v(name)
     WHERE EXISTS (SELECT 1 FROM cols WHERE column_name=v.name)
     ORDER BY
       CASE name
         WHEN 'ts' THEN 1
         WHEN 'ts_utc' THEN 2
         WHEN 'event_ts' THEN 3
         WHEN 'gps_ts' THEN 4
         WHEN 'fix_ts' THEN 5
         WHEN 'event_time' THEN 6
         WHEN 'gps_time' THEN 7
         WHEN 'created_at' THEN 8
         WHEN 'created_ts' THEN 9
         WHEN 'received_at' THEN 10
         WHEN 'inserted_at' THEN 11
         ELSE 12
       END
     LIMIT 1) AS ts_col
),
stmts AS (
  SELECT format(
    'CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON public.driver_telemetry (%I, %I DESC);',
    'ix_driver_telemetry_'||id_col||'_'||ts_col||'_desc',
    id_col, ts_col
  ) AS ddl
  FROM pick
  WHERE to_regclass('public.driver_telemetry') IS NOT NULL
    AND id_col IS NOT NULL
    AND ts_col IS NOT NULL
)
SELECT ddl FROM stmts;
\gexec

SELECT 'ANALYZE public.driver_telemetry;' WHERE to_regclass('public.driver_telemetry') IS NOT NULL;
\gexec

-- FoxProFlow • LANE-C • Preflight Inventory & Forensics
-- file: scripts/sql/fixpacks/20251219_lane_c_preflight_inventory.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--  - READ-ONLY (no DDL). Safe to run multiple times.
--  - Purpose:
--      1) inventory matviews/indexes + concurrent-ready checks
--      2) quick forensics for incidents like:
--         - relation "public.driver_telemetry" does not exist
--         - column "alias" does not exist (region_aliases alias lookup)
-- Preconditions: none
-- Rollback: not needed (read-only)

\set ON_ERROR_STOP on
\pset pager off

-- 0) Runtime context
SELECT
  now() AS ts_now,
  current_database() AS db,
  current_user AS db_user,
  inet_server_addr() AS server_addr,
  inet_server_port() AS server_port,
  current_setting('TimeZone', true) AS timezone;

SHOW server_version;
SHOW server_version_num;

-- 0b) Extensions inventory (helps understand availability of pg_stat_statements, etc.)
SELECT extname, extversion
FROM pg_extension
ORDER BY 1;

-- 0c) Active non-idle queries (helps diagnose lock/contention during maintenance)
SELECT
  pid,
  usename,
  application_name,
  client_addr,
  state,
  wait_event_type,
  wait_event,
  now() - query_start AS age,
  left(query, 220) AS query_snip
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND state IS DISTINCT FROM 'idle'
ORDER BY age DESC
LIMIT 20;

-- 1) Matviews list
SELECT schemaname, matviewname, ispopulated
FROM pg_matviews
WHERE schemaname NOT IN ('pg_catalog','information_schema')
ORDER BY 1,2;

-- 2) Matviews: indexes (including unique + definition)
SELECT i.schemaname, i.tablename AS matview, i.indexname, i.indexdef
FROM pg_indexes i
JOIN pg_matviews mv
  ON mv.schemaname=i.schemaname AND mv.matviewname=i.tablename
WHERE i.schemaname NOT IN ('pg_catalog','information_schema')
ORDER BY 1,2,3;

-- 3) Concurrent readiness (unique + valid + NOT partial)
WITH m AS (
  SELECT mv.schemaname, mv.matviewname, c.oid AS relid
  FROM pg_matviews mv
  JOIN pg_class c ON c.relname=mv.matviewname
  JOIN pg_namespace n ON n.oid=c.relnamespace AND n.nspname=mv.schemaname
  WHERE mv.schemaname NOT IN ('pg_catalog','information_schema')
),
idx AS (
  SELECT m.schemaname, m.matviewname,
         i.relname AS indexname,
         ix.indisunique, ix.indisvalid,
         (ix.indpred IS NOT NULL) AS is_partial
  FROM m
  JOIN pg_index ix ON ix.indrelid=m.relid
  JOIN pg_class i ON i.oid=ix.indexrelid
)
SELECT schemaname, matviewname,
       bool_or(indisunique AND indisvalid AND NOT is_partial) AS has_unique_nonpartial,
       string_agg(
         CASE
           WHEN indisunique THEN indexname || CASE WHEN is_partial THEN ' (partial)' ELSE '' END
           ELSE NULL
         END,
         ', ' ORDER BY indexname
       ) FILTER (WHERE indisunique) AS unique_indexes
FROM idx
GROUP BY 1,2
ORDER BY 1,2;

-- 4) Any invalid/partial unique indexes (risk for CONCURRENT refresh)
WITH m AS (
  SELECT mv.schemaname, mv.matviewname, c.oid AS relid
  FROM pg_matviews mv
  JOIN pg_class c ON c.relname=mv.matviewname
  JOIN pg_namespace n ON n.oid=c.relnamespace AND n.nspname=mv.schemaname
  WHERE mv.schemaname NOT IN ('pg_catalog','information_schema')
),
idx AS (
  SELECT m.schemaname, m.matviewname,
         i.relname AS indexname,
         ix.indisunique, ix.indisvalid,
         (ix.indpred IS NOT NULL) AS is_partial
  FROM m
  JOIN pg_index ix ON ix.indrelid=m.relid
  JOIN pg_class i ON i.oid=ix.indexrelid
)
SELECT schemaname, matviewname, indexname, indisunique, indisvalid, is_partial
FROM idx
WHERE indisunique AND (NOT indisvalid OR is_partial)
ORDER BY 1,2,3;

-- 4b) Matviews without any UNIQUE index (should be empty for concurrent-refresh readiness)
WITH m AS (
  SELECT mv.schemaname, mv.matviewname, c.oid AS relid
  FROM pg_matviews mv
  JOIN pg_class c ON c.relname=mv.matviewname
  JOIN pg_namespace n ON n.oid=c.relnamespace AND n.nspname=mv.schemaname
  WHERE mv.schemaname NOT IN ('pg_catalog','information_schema')
),
has_u AS (
  SELECT m.schemaname, m.matviewname,
         bool_or(ix.indisunique) AS has_unique_any
  FROM m
  LEFT JOIN pg_index ix ON ix.indrelid=m.relid
  GROUP BY 1,2
)
SELECT schemaname, matviewname
FROM has_u
WHERE NOT has_unique_any
ORDER BY 1,2;

-- 5) Existence checks for objects mentioned in incidents
SELECT
  to_regclass('public.driver_telemetry')  AS public_driver_telemetry,
  to_regclass('ops.driver_alerts')        AS ops_driver_alerts,
  to_regclass('public.region_aliases')    AS public_region_aliases;

-- 6) Where does column 'alias' exist at all? (helps quickly debug "column alias does not exist")
SELECT table_schema, table_name
FROM information_schema.columns
WHERE column_name = 'alias'
  AND table_schema NOT IN ('pg_catalog','information_schema')
ORDER BY 1,2;

-- 6b) Column inventory for key objects (helps match real schemas)
SELECT 'public.region_aliases' AS obj, column_name, data_type, ordinal_position
FROM information_schema.columns
WHERE table_schema='public' AND table_name='region_aliases'
ORDER BY ordinal_position;

SELECT 'ops.driver_alerts' AS obj, column_name, data_type, ordinal_position
FROM information_schema.columns
WHERE table_schema='ops' AND table_name='driver_alerts'
ORDER BY ordinal_position;

SELECT 'public.driver_telemetry' AS obj, column_name, data_type, ordinal_position
FROM information_schema.columns
WHERE table_schema='public' AND table_name='driver_telemetry'
ORDER BY ordinal_position;

-- 7) Quick search: views & matviews definitions containing driver_telemetry / region_aliases / alias
-- (string search; forensics only)
SELECT
  n.nspname AS schema,
  c.relname AS relname,
  c.relkind,
  left(pg_get_viewdef(c.oid, true), 400) AS viewdef_snip
FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('v','m')
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND (
    pg_get_viewdef(c.oid, true) ILIKE '%driver_telemetry%'
    OR pg_get_viewdef(c.oid, true) ILIKE '%region_aliases%'
    OR pg_get_viewdef(c.oid, true) ILIKE '%"alias"%'
    OR pg_get_viewdef(c.oid, true) ILIKE '% alias %'
  )
ORDER BY 1,2;

-- 8) Quick search: functions/procedures containing driver_telemetry / region_aliases / alias
-- IMPORTANT: exclude aggregates (prokind='a') to avoid errors like:
--   ERROR: "array_agg" is an aggregate function
SELECT
  n.nspname AS schema,
  p.proname AS proc_name,
  p.prokind,
  format('%I.%I(%s)', n.nspname, p.proname, pg_get_function_identity_arguments(p.oid)) AS signature,
  left(pg_get_functiondef(p.oid), 400) AS funcdef_snip
FROM pg_proc p
JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema')
  AND p.prokind <> 'a'
  AND (
    pg_get_functiondef(p.oid) ILIKE '%driver_telemetry%'
    OR pg_get_functiondef(p.oid) ILIKE '%region_aliases%'
    OR pg_get_functiondef(p.oid) ILIKE '%"alias"%'
    OR pg_get_functiondef(p.oid) ILIKE '% alias %'
  )
ORDER BY 1,2,4;

-- 9) Tables referencing keywords in column names (helps find “nearby” schema objects)
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog','information_schema')
  AND (
    column_name ILIKE '%alias%'
    OR column_name ILIKE '%telemetry%'
    OR column_name ILIKE '%tractor%'
    OR column_name ILIKE '%truck%'
    OR column_name ILIKE '%vehicle%'
  )
ORDER BY 1,2,3;

-- 10) Quick sanity: top relations by size (helps understand where bloat/IO might be)
SELECT
  n.nspname AS schema,
  c.relname AS relname,
  c.relkind,
  pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema')
  AND c.relkind IN ('r','m','i') -- table, matview, index
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 30;

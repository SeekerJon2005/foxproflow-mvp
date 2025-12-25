-- FoxProFlow • DB State Probe • 2025-12-19
-- file: scripts/sql/fixpacks/20251219_db_state_probe.sql

\echo '=== FoxProFlow DB State Probe ==='
SELECT now() AS ts, current_database() AS db, current_user AS db_user, inet_server_addr() AS server_addr;

\echo ''
\echo '--- Migration trackers (presence) ---'
SELECT n.nspname AS schema_name, c.relname AS table_name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND c.relname IN ('alembic_version','schema_migrations','flyway_schema_history')
ORDER BY 1,2;

\echo ''
\echo '--- Materialized views (catalog) ---'
SELECT
  n.nspname AS schema_name,
  c.relname AS matview_name,
  c.relispopulated AS is_populated,
  pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind='m'
  AND n.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY 1,2;

\echo ''
\echo '--- Matviews NOT populated (count) ---'
SELECT count(*) AS matviews_not_populated
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind='m'
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND NOT c.relispopulated;

\echo ''
\echo '--- ops alert tables (if diag view exists) ---'
SELECT CASE WHEN to_regclass('ops.v_ff_diag_ops_alert_tables') IS NOT NULL THEN 1 ELSE 0 END AS has_ops_alert_view \gset
\if :has_ops_alert_view
  SELECT *
  FROM ops.v_ff_diag_ops_alert_tables
  ORDER BY total_bytes DESC NULLS LAST
  LIMIT 30;
\else
  \echo 'NOTICE: ops.v_ff_diag_ops_alert_tables not found (apply migration 20251219_ops_diag_views.sql first)'
\endif

\echo '=== END DB State Probe ==='

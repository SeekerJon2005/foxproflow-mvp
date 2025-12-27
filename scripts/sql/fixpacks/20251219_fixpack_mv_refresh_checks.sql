-- FoxProFlow • SQL Fix Pack • MV refresh checks • 2025-12-19
-- file: scripts/sql/fixpacks/20251219_fixpack_mv_refresh_checks.sql

\echo '=== MV Refresh Fix Pack CHECKS ==='

\echo ''
\echo '--- Matviews NOT populated (count) ---'
SELECT count(*) AS matviews_not_populated
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind='m'
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND NOT c.relispopulated;

\echo ''
\echo '--- Matviews NOT populated (list) ---'
SELECT n.nspname AS schema_name, c.relname AS matview_name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind='m'
  AND n.nspname NOT IN ('pg_catalog','information_schema')
  AND NOT c.relispopulated
ORDER BY 1,2;

\echo ''
\echo '--- ops diag views (if exist) ---'
SELECT CASE WHEN to_regclass('ops.v_ff_diag_matviews_health') IS NOT NULL THEN 1 ELSE 0 END AS has_mv_health \gset
\if :has_mv_health
  SELECT * FROM ops.v_ff_diag_matviews_health
  ORDER BY is_populated ASC, total_bytes DESC, schema_name, matview_name;
\else
  \echo 'NOTICE: ops.v_ff_diag_matviews_health not found (apply migration 20251219_ops_diag_views.sql first)'
\endif

SELECT CASE WHEN to_regclass('ops.v_ff_diag_matviews_concurrent_ready') IS NOT NULL THEN 1 ELSE 0 END AS has_mv_ready \gset
\if :has_mv_ready
  SELECT * FROM ops.v_ff_diag_matviews_concurrent_ready
  ORDER BY concurrent_refresh_ready ASC, schema_name, matview_name;
\else
  \echo 'NOTICE: ops.v_ff_diag_matviews_concurrent_ready not found (apply migration 20251219_ops_diag_views.sql first)'
\endif

SELECT CASE WHEN to_regclass('ops.v_ff_diag_ops_alert_tables') IS NOT NULL THEN 1 ELSE 0 END AS has_ops_alert_view \gset
\if :has_ops_alert_view
  SELECT * FROM ops.v_ff_diag_ops_alert_tables
  ORDER BY total_bytes DESC NULLS LAST
  LIMIT 30;
\else
  \echo 'NOTICE: ops.v_ff_diag_ops_alert_tables not found (apply migration 20251219_ops_diag_views.sql first)'
\endif

\echo '=== END CHECKS ==='

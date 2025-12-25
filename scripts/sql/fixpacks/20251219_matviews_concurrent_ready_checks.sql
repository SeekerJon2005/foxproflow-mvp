-- FoxProFlow • FixPack • Checks: matviews concurrent readiness
-- file: scripts/sql/fixpacks/20251219_matviews_concurrent_ready_checks.sql

\echo '=== FixPack CHECKS: Matviews CONCURRENT readiness ==='

\echo ''
\echo '--- Ready counts ---'
SELECT concurrent_refresh_ready, count(*) AS cnt
FROM ops.v_ff_diag_matviews_concurrent_ready
GROUP BY 1
ORDER BY 1;

\echo ''
\echo '--- Not ready list (should become empty for our 6) ---'
SELECT schema_name, matview_name, usable_unique_indexes
FROM ops.v_ff_diag_matviews_concurrent_ready
WHERE NOT concurrent_refresh_ready
ORDER BY 1,2;

\echo ''
\echo '--- Our 6 targets (detailed) ---'
SELECT *
FROM ops.v_ff_diag_matviews_concurrent_ready
WHERE (schema_name, matview_name) IN (
  ('analytics','devfactory_dev_tasks_flow_daily_df3_mv'),
  ('analytics','devfactory_task_kpi_v2'),
  ('analytics','logistics_ontime_delivery_kpi_daily'),
  ('public','driver_history_mv'),
  ('public','freights_enriched_mv_v2'),
  ('public','freights_price_distance_norm_mv')
)
ORDER BY schema_name, matview_name;

\echo '=== END CHECKS ==='

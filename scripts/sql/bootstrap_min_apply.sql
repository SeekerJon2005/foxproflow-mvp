\pset pager off
\set ON_ERROR_STOP on

\echo '---'
\echo 'BOOTSTRAP MIN APPLY START'
\echo '---'

-- 1) Core minimal baseline (sec/dev/ops/planner)
\ir fixpacks/20251222_db_bootstrap_min_apply.sql

-- 2) Gate M0 DB contract prerequisite
\ir fixpacks/20251224_ops_agent_events_apply.sql

-- 3) Logistics minimal + availability MV prerequisites
\ir fixpacks/20251221_logistics_bootstrap_min_apply.sql
\ir fixpacks/20251226_trip_segments_region_cols_compat_apply.sql
\ir fixpacks/20251221_booking_windows_and_availability_apply.sql
\ir fixpacks/20251221_vehicle_availability_indexes_apply.sql

-- 4) DevFactory baseline + KPI MV definition (DDL only, no refresh inside patch!)
\ir fixpacks/20251224_m0_devfactory_contract_apply.sql
\ir fixpacks/20251227_analytics_devfactory_task_kpi_v2_ddl_apply.sql

-- 4a) CRITICAL: first populate KPI MV WITHOUT CONCURRENTLY (Postgres requirement)
\echo INFO: first populate analytics.devfactory_task_kpi_v2 (no CONCURRENTLY)
REFRESH MATERIALIZED VIEW analytics.devfactory_task_kpi_v2;
ANALYZE analytics.devfactory_task_kpi_v2;

-- 4b) Ensure UNIQUE index for future CONCURRENT refresh readiness
\ir fixpacks/20251224_devfactory_task_kpi_v2_unique_index_apply.sql

\echo '---'
\echo 'BOOTSTRAP MIN APPLY DONE'
\echo '---'


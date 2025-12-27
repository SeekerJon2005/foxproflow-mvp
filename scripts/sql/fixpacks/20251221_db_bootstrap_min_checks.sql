-- FoxProFlow • DB bootstrap MIN • CHECKS
-- file: scripts/sql/fixpacks/20251221_db_bootstrap_min_checks.sql
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\echo '=== FoxProFlow DB Bootstrap MIN CHECKS ==='
SELECT now() AS ts, current_database() AS db, current_user AS db_user;

\echo ''
\echo '--- Existence (must be t) ---'
SELECT 'sec.roles'                 AS obj, (to_regclass('sec.roles') IS NOT NULL)                 AS ok;
SELECT 'sec.subject_roles'         AS obj, (to_regclass('sec.subject_roles') IS NOT NULL)         AS ok;
SELECT 'sec.policies'              AS obj, (to_regclass('sec.policies') IS NOT NULL)              AS ok;
SELECT 'sec.role_policy_bindings'  AS obj, (to_regclass('sec.role_policy_bindings') IS NOT NULL)  AS ok;

SELECT 'dev.dev_task'              AS obj, (to_regclass('dev.dev_task') IS NOT NULL)              AS ok;

SELECT 'ops.event_log'             AS obj, (to_regclass('ops.event_log') IS NOT NULL)             AS ok;

SELECT 'planner.kpi_snapshots'     AS obj, (to_regclass('planner.kpi_snapshots') IS NOT NULL)     AS ok;
SELECT 'planner.planner_kpi_daily' AS obj, (to_regclass('planner.planner_kpi_daily') IS NOT NULL) AS ok;

\echo ''
\echo '--- Planner callable presence ---'
SELECT to_regprocedure('planner.kpi_snapshot()') IS NOT NULL AS has_planner_kpi_snapshot;

\echo ''
\echo '--- Seeds sanity (counts) ---'
SELECT 'sec.roles' AS obj, count(*) AS cnt FROM sec.roles;
SELECT 'sec.subject_roles' AS obj, count(*) AS cnt FROM sec.subject_roles;
SELECT 'sec.policies' AS obj, count(*) AS cnt FROM sec.policies;
SELECT 'sec.role_policy_bindings' AS obj, count(*) AS cnt FROM sec.role_policy_bindings;

\echo ''
\echo '--- Column inventory: dev.dev_task ---'
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='dev' AND table_name='dev_task'
ORDER BY ordinal_position;

\echo ''
\echo '--- Column inventory: ops.event_log ---'
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='ops' AND table_name='event_log'
ORDER BY ordinal_position;

\echo ''
\echo '--- Quick non-destructive call test: planner.kpi_snapshot() (BEGIN/ROLLBACK) ---'
BEGIN;
SELECT planner.kpi_snapshot();
ROLLBACK;

\echo '=== END CHECKS ==='

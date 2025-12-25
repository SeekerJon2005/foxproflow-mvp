-- file: scripts/sql/verify/20251222_db_bootstrap_min_postcheck.sql
-- FoxProFlow • Verify • DB BOOTSTRAP MIN post-check

\set ON_ERROR_STOP on
\pset pager off

SELECT
  to_regclass('public.alembic_version')     AS alembic_version,
  to_regclass('public.schema_migrations')   AS schema_migrations,
  to_regclass('dev.dev_task')               AS dev_task,
  to_regclass('ops.event_log')              AS ops_event_log,
  to_regclass('planner.kpi_snapshots')      AS kpi_snapshots,
  to_regclass('planner.planner_kpi_daily')  AS kpi_daily;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='dev' AND table_name='dev_task'
  AND column_name IN ('source','project_ref','language','channel','error','links','meta')
ORDER BY column_name;

SELECT
  a.attname,
  pg_get_expr(ad.adbin, ad.adrelid) AS column_default
FROM pg_attribute a
LEFT JOIN pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum
WHERE a.attrelid='dev.dev_task'::regclass
  AND a.attname='id'
  AND NOT a.attisdropped;

-- sanity: ops.event_log correlation_id exists
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='ops' AND table_name='event_log' AND column_name='correlation_id';

SELECT planner.kpi_snapshot();
REFRESH MATERIALIZED VIEW planner.planner_kpi_daily;
SELECT * FROM planner.planner_kpi_daily ORDER BY day DESC LIMIT 3;

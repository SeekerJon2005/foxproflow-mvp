-- file: scripts/sql/verify/20251222_db_bootstrap_min_smoke.sql
-- FoxProFlow • Verify/Smoke • DB BOOTSTRAP MIN
-- Created by: Архитектор Яцков Евгений Анатольевич

\set ON_ERROR_STOP on
\pset pager off

SELECT
  now() AS ts_now,
  current_database() AS db,
  current_user AS db_user,
  current_setting('server_version', true) AS server_version,
  version() AS pg_version;

SHOW search_path;

SELECT
  to_regclass('public.alembic_version')        AS alembic_version,
  to_regclass('public.schema_migrations')      AS schema_migrations,
  to_regclass('sec.roles')                     AS sec_roles,
  to_regclass('sec.subject_roles')             AS sec_subject_roles,
  to_regclass('sec.policies')                  AS sec_policies,
  to_regclass('sec.role_policy_bindings')      AS sec_role_policy_bindings,
  to_regclass('dev.dev_task')                  AS dev_task,
  to_regclass('ops.event_log')                 AS ops_event_log,
  to_regclass('planner.kpi_snapshots')         AS kpi_snapshots,
  to_regclass('planner.planner_kpi_daily')     AS kpi_daily;

SELECT
  (SELECT count(*) FROM public.alembic_version)      AS alembic_rows,
  (SELECT count(*) FROM public.schema_migrations)    AS schema_migrations_rows;

SELECT
  (SELECT count(*) FROM sec.roles)                 AS sec_roles_cnt,
  (SELECT count(*) FROM sec.subject_roles)         AS sec_subject_roles_cnt,
  (SELECT count(*) FROM sec.policies)              AS sec_policies_cnt,
  (SELECT count(*) FROM sec.role_policy_bindings)  AS sec_role_policy_bindings_cnt;

SELECT id, role_code, code, name, is_active, created_at
FROM sec.roles
WHERE role_code='architect' OR code='architect'
ORDER BY id
LIMIT 5;

SELECT policy_code, effect, domain, action, is_active, created_at
FROM sec.policies
WHERE policy_code IN ('devfactory.view_tasks.allow', 'devfactory.manage_tasks.allow')
ORDER BY policy_code;

SELECT role_code, policy_code, is_active, created_at
FROM sec.role_policy_bindings
WHERE role_code='architect'
ORDER BY policy_code;

-- DEV: required columns
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='dev' AND table_name='dev_task'
  AND column_name IN ('public_id','stack','title','status','source','project_ref','language','channel','input_spec','result_spec','links','meta','error','created_at','updated_at')
ORDER BY column_name;

-- DEV: defaults
SELECT
  a.attname,
  pg_get_expr(ad.adbin, ad.adrelid) AS column_default
FROM pg_attribute a
LEFT JOIN pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum
WHERE a.attrelid='dev.dev_task'::regclass
  AND a.attname IN ('id','created_at','updated_at')
  AND NOT a.attisdropped
ORDER BY a.attname;

SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='dev' AND tablename='dev_task'
ORDER BY indexname;

-- OPS: columns (incl correlation_id)
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='ops' AND table_name='event_log'
ORDER BY ordinal_position;

SELECT
  a.attname,
  pg_get_expr(ad.adbin, ad.adrelid) AS column_default
FROM pg_attribute a
LEFT JOIN pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum
WHERE a.attrelid='ops.event_log'::regclass
  AND a.attname IN ('id','ts','created_at')
  AND NOT a.attisdropped
ORDER BY a.attname;

SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='ops' AND tablename='event_log'
ORDER BY indexname;

-- PLANNER: call snapshot + refresh MV
SELECT planner.kpi_snapshot();

SELECT count(*) AS snapshots_cnt, max(ts) AS last_ts
FROM planner.kpi_snapshots;

SELECT ts, payload
FROM planner.kpi_snapshots
ORDER BY ts DESC
LIMIT 1;

REFRESH MATERIALIZED VIEW planner.planner_kpi_daily;

SELECT *
FROM planner.planner_kpi_daily
ORDER BY day DESC
LIMIT 5;

SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='planner' AND tablename='planner_kpi_daily'
ORDER BY indexname;

SELECT
  i.relname AS indexname,
  ix.indisunique AS is_unique,
  (ix.indpred IS NULL) AS is_not_partial,
  pg_get_indexdef(i.oid) AS indexdef
FROM pg_class t
JOIN pg_namespace n ON n.oid=t.relnamespace
JOIN pg_index ix ON ix.indrelid=t.oid
JOIN pg_class i ON i.oid=ix.indexrelid
WHERE n.nspname='planner' AND t.relname='planner_kpi_daily'
ORDER BY i.relname;

SELECT day, count(*) AS cnt
FROM planner.planner_kpi_daily
GROUP BY day
HAVING count(*) > 1
ORDER BY cnt DESC, day DESC;

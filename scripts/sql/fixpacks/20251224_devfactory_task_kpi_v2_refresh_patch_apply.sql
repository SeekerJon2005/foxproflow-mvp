-- FoxProFlow • FixPack • SQL-M0 • devfactory_task_kpi_v2 refresh patch
-- file: scripts/sql/fixpacks/20251224_devfactory_task_kpi_v2_refresh_patch_apply.sql
-- Created: 2025-12-24
-- Created by: Архитектор Яцков Евгений Анатольевич
-- DevTask: (set real DevTask id)
-- Purpose:
--   Ensure first refresh is NON-concurrent if MV is not populated,
--   and use CONCURRENTLY only when safe (populated + usable UNIQUE index).
-- Idempotent: yes
-- Rollback: not needed (no schema changes), but can stop calling this fixpack.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';

-- Hard-fail if MV is missing (so pipeline goes red)
DO $$
BEGIN
  IF to_regclass('analytics.devfactory_task_kpi_v2') IS NULL THEN
    RAISE EXCEPTION 'MISSING: analytics.devfactory_task_kpi_v2 (expected by DevFactory KPI).';
  END IF;
END$$;

-- Is populated? (store as true/false for psql \if)
SELECT CASE WHEN c.relispopulated THEN 'true' ELSE 'false' END AS mv_is_populated
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'analytics'
  AND c.relname = 'devfactory_task_kpi_v2'
  AND c.relkind = 'm'
\gset

-- Has usable UNIQUE index for CONCURRENTLY? (indisunique + indisvalid + no predicate)
SELECT CASE WHEN EXISTS (
  SELECT 1
  FROM pg_index i
  JOIN pg_class mv     ON mv.oid = i.indrelid
  JOIN pg_namespace n  ON n.oid = mv.relnamespace
  WHERE n.nspname = 'analytics'
    AND mv.relname = 'devfactory_task_kpi_v2'
    AND mv.relkind = 'm'
    AND i.indisunique
    AND i.indisvalid
    AND i.indpred IS NULL
) THEN 'true' ELSE 'false' END AS mv_concurrent_ready
\gset

\echo INFO: mv_is_populated=:mv_is_populated mv_concurrent_ready=:mv_concurrent_ready

-- Decision tree:
--  1) not populated -> plain refresh
--  2) populated & ready -> concurrently refresh
--  3) populated but not ready -> plain refresh
\if :mv_is_populated
  \if :mv_concurrent_ready
    \echo INFO: refreshing CONCURRENTLY analytics.devfactory_task_kpi_v2
    REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.devfactory_task_kpi_v2;
  \else
    \echo WARN: MV populated but NOT concurrently-ready -> refreshing plain
    REFRESH MATERIALIZED VIEW analytics.devfactory_task_kpi_v2;
  \endif
\else
  \echo INFO: first refresh (MV not populated) -> refreshing plain
  REFRESH MATERIALIZED VIEW analytics.devfactory_task_kpi_v2;
\endif

ANALYZE analytics.devfactory_task_kpi_v2;

\echo OK: refresh patch applied for analytics.devfactory_task_kpi_v2

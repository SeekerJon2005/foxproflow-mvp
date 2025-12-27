-- FoxProFlow • FixPack • SQL • M0+ • devfactory_task_kpi_v2 unique index for CONCURRENTLY refresh
-- file: scripts/sql/fixpacks/20251224_devfactory_task_kpi_v2_unique_index_apply.sql
-- Created: 2025-12-24
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--   Create a valid, unconditional UNIQUE index on analytics.devfactory_task_kpi_v2(project_ref, stack)
--   so REFRESH MATERIALIZED VIEW CONCURRENTLY becomes available.
-- Idempotent: yes

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '30s';
SET statement_timeout = '30min';

-- Preflight: MV must exist
DO $$
BEGIN
  IF to_regclass('analytics.devfactory_task_kpi_v2') IS NULL THEN
    RAISE EXCEPTION 'MISSING: analytics.devfactory_task_kpi_v2';
  END IF;
END$$;

-- Safety: ensure no duplicate keys (should never happen for this GROUP BY MV, but we prove it)
DO $$
DECLARE
  dup_cnt bigint;
BEGIN
  SELECT count(*) INTO dup_cnt
  FROM (
    SELECT project_ref, stack, count(*) AS c
    FROM analytics.devfactory_task_kpi_v2
    GROUP BY 1,2
    HAVING count(*) > 1
  ) d;

  IF dup_cnt > 0 THEN
    RAISE EXCEPTION 'DUPLICATE KEYS: analytics.devfactory_task_kpi_v2 has % duplicate (project_ref, stack) groups', dup_cnt;
  END IF;
END$$;

-- Detect existing index in analytics schema
SELECT CASE WHEN EXISTS (
  SELECT 1
  FROM pg_class idx
  JOIN pg_namespace n ON n.oid = idx.relnamespace
  WHERE n.nspname = 'analytics'
    AND idx.relname = 'ux_devfactory_task_kpi_v2_project_stack'
    AND idx.relkind = 'i'
) THEN 'true' ELSE 'false' END AS idx_exists \gset

-- Detect if that index is valid + unique + unconditional (no predicate)
SELECT CASE WHEN EXISTS (
  SELECT 1
  FROM pg_index i
  JOIN pg_class idx      ON idx.oid = i.indexrelid
  JOIN pg_namespace n    ON n.oid = idx.relnamespace
  WHERE n.nspname = 'analytics'
    AND idx.relname = 'ux_devfactory_task_kpi_v2_project_stack'
    AND i.indisvalid
    AND i.indisunique
    AND i.indpred IS NULL
) THEN 'true' ELSE 'false' END AS idx_valid \gset

\echo INFO: idx_exists=:idx_exists idx_valid=:idx_valid

-- If exists but not valid/unique/unconditional -> drop + recreate
\if :idx_exists
  \if :idx_valid
    \echo INFO: existing valid UNIQUE index found, skipping
  \else
    \echo WARN: existing index found but not valid/unique/unconditional -> dropping concurrently
    DROP INDEX CONCURRENTLY IF EXISTS analytics.ux_devfactory_task_kpi_v2_project_stack;

    \echo INFO: creating UNIQUE index concurrently
    CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_devfactory_task_kpi_v2_project_stack
      ON analytics.devfactory_task_kpi_v2 (project_ref, stack);
  \endif
\else
  \echo INFO: creating UNIQUE index concurrently
  CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_devfactory_task_kpi_v2_project_stack
    ON analytics.devfactory_task_kpi_v2 (project_ref, stack);
\endif

ANALYZE analytics.devfactory_task_kpi_v2;

\echo OK: ensured UNIQUE index for analytics.devfactory_task_kpi_v2 (project_ref, stack)

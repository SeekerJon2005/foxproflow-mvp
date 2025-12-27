-- FoxProFlow • VERIFY • Gate M0 DB contract
-- file: scripts/sql/verify/20251224_gate_m0_db_contract_verify.sql
-- Created: 2025-12-24
-- Created by: Архитектор Яцков Евгений Анатольевич
-- DevTask: (set real DevTask id)
-- PASS marker: OK: Gate M0 DB contract verify passed

\set ON_ERROR_STOP on
\pset pager off

\echo === Gate M0 DB contract verify: START ===

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user, version() AS pg_version;

-- 1) ops.agent_events exists
DO $$
BEGIN
  IF to_regclass('ops.agent_events') IS NULL THEN
    RAISE EXCEPTION 'MISSING: ops.agent_events';
  END IF;
END$$;

-- 1b) ops.agent_events columns (minimal contract)
DO $$
DECLARE
  missing text := '';
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ops' AND table_name='agent_events' AND column_name='ts') THEN
    missing := missing || ' ts';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ops' AND table_name='agent_events' AND column_name='agent') THEN
    missing := missing || ' agent';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ops' AND table_name='agent_events' AND column_name='level') THEN
    missing := missing || ' level';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ops' AND table_name='agent_events' AND column_name='action') THEN
    missing := missing || ' action';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ops' AND table_name='agent_events' AND column_name='payload') THEN
    missing := missing || ' payload';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ops' AND table_name='agent_events' AND column_name='ok') THEN
    missing := missing || ' ok';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ops' AND table_name='agent_events' AND column_name='latency_ms') THEN
    missing := missing || ' latency_ms';
  END IF;

  IF missing <> '' THEN
    RAISE EXCEPTION 'MISSING COLUMNS ops.agent_events:%', missing;
  END IF;
END$$;

\echo OK: ops.agent_events exists + columns ok

-- 2) devfactory_task_kpi_v2 exists
DO $$
BEGIN
  IF to_regclass('analytics.devfactory_task_kpi_v2') IS NULL THEN
    RAISE EXCEPTION 'MISSING: analytics.devfactory_task_kpi_v2';
  END IF;
END$$;

-- 3) refresh logic flags as true/false for psql \if
SELECT CASE WHEN c.relispopulated THEN 'true' ELSE 'false' END AS mv_is_populated
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname='analytics'
  AND c.relname='devfactory_task_kpi_v2'
  AND c.relkind='m'
\gset

SELECT CASE WHEN EXISTS (
  SELECT 1
  FROM pg_index i
  JOIN pg_class mv     ON mv.oid = i.indrelid
  JOIN pg_namespace n  ON n.oid = mv.relnamespace
  WHERE n.nspname='analytics'
    AND mv.relname='devfactory_task_kpi_v2'
    AND mv.relkind='m'
    AND i.indisunique
    AND i.indisvalid
    AND i.indpred IS NULL
) THEN 'true' ELSE 'false' END AS mv_concurrent_ready
\gset

\echo INFO: mv_is_populated=:mv_is_populated mv_concurrent_ready=:mv_concurrent_ready

-- Ensure populated (plain if needed)
\if :mv_is_populated
  \echo INFO: MV already populated
\else
  \echo INFO: MV not populated -> plain refresh
  REFRESH MATERIALIZED VIEW analytics.devfactory_task_kpi_v2;
\endif

-- Concurrent refresh test only when it SHOULD work
\if :mv_concurrent_ready
  \echo INFO: MV concurrently-ready -> concurrent refresh test
  REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.devfactory_task_kpi_v2;
\else
  \echo WARN: MV not concurrently-ready -> skipping concurrent refresh test
\endif

-- Key query must work
SELECT count(*) AS devfactory_task_kpi_v2_rows
FROM analytics.devfactory_task_kpi_v2;

\echo OK: Gate M0 DB contract verify passed
\echo === Gate M0 DB contract verify: END ===

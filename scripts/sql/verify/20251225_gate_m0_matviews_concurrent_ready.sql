-- FoxProFlow • Gate M0+ • Matviews CONCURRENTLY-ready Verify
-- file: scripts/sql/verify/20251225_gate_m0_matviews_concurrent_ready.sql
-- lane: C-SQL / DATA / CONTRACTS
-- owner: Архитектор Яцков Евгений Анатольевич
--
-- Goal:
--   Ensure required materialized views exist and are safe for:
--     REFRESH MATERIALIZED VIEW CONCURRENTLY
--   Requirements:
--     - matview exists
--     - ispopulated = true
--     - has at least one UNIQUE index that is:
--         indisunique = true
--         indisvalid  = true
--         indisready  = true
--         indpred IS NULL  (non-partial)

\pset pager off
\set ON_ERROR_STOP on

SELECT 'verify:gate_m0_matviews_concurrent_ready:begin' AS _;

DO $$
DECLARE
  mv record;
  missing text[] := ARRAY[]::text[];
  not_populated text[] := ARRAY[]::text[];
  not_ready text[] := ARRAY[]::text[];
  ok boolean;
BEGIN
  FOR mv IN
    SELECT * FROM (VALUES
      ('analytics'::text,'devfactory_task_kpi_v2'::text),
      ('planner'::text,'planner_kpi_daily'::text),
      ('public'::text,'vehicle_availability_mv'::text)
    ) AS t(schemaname, matviewname)
  LOOP
    -- exists?
    IF NOT EXISTS (
      SELECT 1
        FROM pg_matviews m
       WHERE m.schemaname = mv.schemaname
         AND m.matviewname = mv.matviewname
    ) THEN
      missing := array_append(missing, mv.schemaname||'.'||mv.matviewname);
      CONTINUE;
    END IF;

    -- populated?
    IF NOT EXISTS (
      SELECT 1
        FROM pg_matviews m
       WHERE m.schemaname = mv.schemaname
         AND m.matviewname = mv.matviewname
         AND m.ispopulated = true
    ) THEN
      not_populated := array_append(not_populated, mv.schemaname||'.'||mv.matviewname);
    END IF;

    -- concurrently-ready strict unique index?
    SELECT EXISTS (
      SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_index ix ON ix.indrelid = c.oid
       WHERE c.relkind = 'm'
         AND n.nspname = mv.schemaname
         AND c.relname = mv.matviewname
         AND ix.indisunique = true
         AND ix.indisvalid  = true
         AND ix.indisready  = true
         AND ix.indpred IS NULL
    ) INTO ok;

    IF NOT ok THEN
      not_ready := array_append(not_ready, mv.schemaname||'.'||mv.matviewname);
    END IF;

  END LOOP;

  IF array_length(missing,1) IS NOT NULL THEN
    RAISE NOTICE 'HINT: if this is a fresh DB, run bootstrap_min apply / relevant fixpacks first';
    RAISE EXCEPTION 'MISSING_MATVIEWS: %', array_to_string(missing, ', ');
  END IF;

  IF array_length(not_populated,1) IS NOT NULL THEN
    RAISE EXCEPTION 'MATVIEWS_NOT_POPULATED: %', array_to_string(not_populated, ', ');
  END IF;

  IF array_length(not_ready,1) IS NOT NULL THEN
    RAISE NOTICE 'HINT: ensure each matview has a UNIQUE, valid, ready, non-partial index';
    RAISE EXCEPTION 'MATVIEWS_NOT_CONCURRENT_READY: %', array_to_string(not_ready, ', ');
  END IF;

END $$;

SELECT 'verify:gate_m0_matviews_concurrent_ready:ok' AS _;

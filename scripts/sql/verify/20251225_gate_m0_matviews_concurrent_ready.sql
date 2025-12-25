-- FoxProFlow • VERIFY • MatViews CONCURRENT refresh readiness (M0+)
-- file: scripts/sql/verify/20251225_gate_m0_matviews_concurrent_ready.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes: READ-ONLY. Fail-fast. Prints explicit OK marker on success.
--        Requirement for REFRESH MATERIALIZED VIEW CONCURRENTLY:
--          - matview exists
--          - relispopulated = true
--          - unique valid non-partial index exists (indisunique + indisvalid + indpred is null)

\set ON_ERROR_STOP on
\pset pager off

DO $$
DECLARE
  missing     text[] := ARRAY[]::text[];
  not_matview text[] := ARRAY[]::text[];
  unpop       text[] := ARRAY[]::text[];
  no_unique   text[] := ARRAY[]::text[];
BEGIN
  -- Contract list for M0+ (align with what реально живёт в БД и нужно для evidence/KPI)
  WITH required AS (
    SELECT unnest(ARRAY[
      'analytics.devfactory_task_kpi_v2',
      'planner.planner_kpi_daily',
      'public.vehicle_availability_mv'
    ]) AS rel
  ),
  cls AS (
    SELECT
      r.rel,
      to_regclass(r.rel) AS reg,
      c.oid AS rel_oid,
      c.relkind,
      c.relispopulated AS ispopulated
    FROM required r
    LEFT JOIN pg_class c ON c.oid = to_regclass(r.rel)
  )
  SELECT
    array_agg(rel) FILTER (WHERE reg IS NULL),
    array_agg(rel) FILTER (WHERE reg IS NOT NULL AND relkind IS DISTINCT FROM 'm'),
    array_agg(rel) FILTER (WHERE reg IS NOT NULL AND relkind = 'm' AND ispopulated IS DISTINCT FROM true),
    array_agg(rel) FILTER (
      WHERE reg IS NOT NULL AND relkind = 'm' AND NOT EXISTS (
        SELECT 1
        FROM pg_index ix
        WHERE ix.indrelid = rel_oid
          AND ix.indisunique
          AND ix.indisvalid
          AND ix.indpred IS NULL
      )
    )
  INTO missing, not_matview, unpop, no_unique
  FROM cls;

  IF array_length(missing, 1) IS NOT NULL THEN
    RAISE EXCEPTION 'MISSING_MATVIEWS: %', array_to_string(missing, ', ');
  END IF;

  IF array_length(not_matview, 1) IS NOT NULL THEN
    RAISE EXCEPTION 'NOT_MATVIEW: %', array_to_string(not_matview, ', ');
  END IF;

  IF array_length(unpop, 1) IS NOT NULL THEN
    RAISE EXCEPTION 'UNPOPULATED_MATVIEWS: % (run first REFRESH without CONCURRENTLY)', array_to_string(unpop, ', ');
  END IF;

  IF array_length(no_unique, 1) IS NOT NULL THEN
    RAISE EXCEPTION 'NO_UNIQUE_INDEX_FOR_CONCURRENT_REFRESH: %', array_to_string(no_unique, ', ');
  END IF;
END $$;

\echo OK: MatViews CONCURRENT readiness passed

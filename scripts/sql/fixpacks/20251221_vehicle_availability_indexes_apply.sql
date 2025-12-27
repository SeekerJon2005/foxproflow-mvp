-- FoxProFlow • FixPack
-- file: scripts/sql/fixpacks/20251221_vehicle_availability_indexes_apply.sql
-- lane: C-SQL / DATA / CONTRACTS
-- owner: Архитектор Яцков Евгений Анатольевич
--
-- Purpose:
--   Ensure performance indexes for public.vehicle_availability_mv.
--   Compatibility:
--     - supports new column: available_region
--     - supports legacy column: last_unloading_region
--     - supports legacy column: last_unload_region
--
-- Notes:
--   - This fixpack does NOT enforce CONCURRENT refresh readiness (UNIQUE index).
--     That responsibility is handled by:
--       scripts/sql/fixpacks/20251226_vehicle_availability_mv_uidx_apply.sql
--
-- Important:
--   Use pg_catalog (pg_attribute) to detect columns because information_schema
--   may not reliably expose matview columns.

\pset pager off
\set ON_ERROR_STOP on

SELECT pg_advisory_lock(hashtext('ff:fixpack:vehicle_availability_indexes')::bigint);

DO $$
DECLARE
  rel regclass;
  rk  "char";
  col_region text;

  has_truck_id boolean := false;
  has_available_from boolean := false;
  has_available_region boolean := false;
  has_last_unloading_region boolean := false;
  has_last_unload_region boolean := false;
BEGIN
  rel := to_regclass('public.vehicle_availability_mv');
  IF rel IS NULL THEN
    RAISE NOTICE 'SKIP: public.vehicle_availability_mv is missing';
    RETURN;
  END IF;

  SELECT c.relkind INTO rk
    FROM pg_class c
   WHERE c.oid = rel;

  IF rk NOT IN ('r','m') THEN
    RAISE NOTICE 'SKIP: public.vehicle_availability_mv relkind=% (expected table or matview)', rk::text;
    RETURN;
  END IF;

  -- Detect columns via pg_attribute (works for matviews)
  SELECT EXISTS (
    SELECT 1 FROM pg_attribute a
    WHERE a.attrelid = rel
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND a.attname = 'truck_id'
  ) INTO has_truck_id;

  SELECT EXISTS (
    SELECT 1 FROM pg_attribute a
    WHERE a.attrelid = rel
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND a.attname = 'available_from'
  ) INTO has_available_from;

  SELECT EXISTS (
    SELECT 1 FROM pg_attribute a
    WHERE a.attrelid = rel
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND a.attname = 'available_region'
  ) INTO has_available_region;

  SELECT EXISTS (
    SELECT 1 FROM pg_attribute a
    WHERE a.attrelid = rel
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND a.attname = 'last_unloading_region'
  ) INTO has_last_unloading_region;

  SELECT EXISTS (
    SELECT 1 FROM pg_attribute a
    WHERE a.attrelid = rel
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND a.attname = 'last_unload_region'
  ) INTO has_last_unload_region;

  -- truck_id
  IF has_truck_id THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_vehicle_availability_truck ON public.vehicle_availability_mv USING btree (truck_id)';
  ELSE
    RAISE NOTICE 'SKIP: column truck_id not found on public.vehicle_availability_mv';
  END IF;

  -- available_from
  IF has_available_from THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_vehicle_availability_from ON public.vehicle_availability_mv USING btree (available_from)';
  ELSE
    RAISE NOTICE 'SKIP: column available_from not found on public.vehicle_availability_mv';
  END IF;

  -- region column (compat)
  IF has_available_region THEN
    col_region := 'available_region';
  ELSIF has_last_unloading_region THEN
    col_region := 'last_unloading_region';
  ELSIF has_last_unload_region THEN
    col_region := 'last_unload_region';
  ELSE
    col_region := NULL;
  END IF;

  IF col_region IS NOT NULL THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_vehicle_availability_region ON public.vehicle_availability_mv USING btree ('||
            quote_ident(col_region)||')';
  ELSE
    RAISE NOTICE 'SKIP: no region column found (available_region/last_unloading_region/last_unload_region)';
  END IF;

  EXECUTE 'ANALYZE public.vehicle_availability_mv';
  RAISE NOTICE 'OK: ensured vehicle_availability_mv perf indexes (truck_id/available_from/region if present)';
END $$;

SELECT pg_advisory_unlock(hashtext('ff:fixpack:vehicle_availability_indexes')::bigint);

SELECT 'OK: 20251221_vehicle_availability_indexes_apply (compat pg_attribute)' AS _;

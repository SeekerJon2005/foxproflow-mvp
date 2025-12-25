-- FoxProFlow • FixPack • Region columns for routing/planning
-- file: scripts/sql/fixpacks/20251221_public_region_columns_apply.sql
-- DEVTASK: 348
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--   Adds loading_region/unloading_region columns (text) to public.{trips,trip_segments,loads}.
--   Creates simple btree indexes (non-CONCURRENTLY; suitable for dev/local).
--   Idempotent: safe to run multiple times.

-- Safety: avoid hanging on locks forever during DDL
SET lock_timeout = '5s';
SET statement_timeout = '10min';
SET client_min_messages = NOTICE;

-- 1) Columns (skip cleanly if a table is missing)
ALTER TABLE IF EXISTS public.trips
  ADD COLUMN IF NOT EXISTS loading_region text,
  ADD COLUMN IF NOT EXISTS unloading_region text;

ALTER TABLE IF EXISTS public.trip_segments
  ADD COLUMN IF NOT EXISTS loading_region text,
  ADD COLUMN IF NOT EXISTS unloading_region text;

ALTER TABLE IF EXISTS public.loads
  ADD COLUMN IF NOT EXISTS loading_region text,
  ADD COLUMN IF NOT EXISTS unloading_region text;

-- 2) Indexes (only if relation is a table/partitioned table)
DO $$
DECLARE
  rk text;

  -- helper: get relkind for a qualified relation
  -- relkind: 'r' ordinary table, 'p' partitioned table, 'v' view, 'm' matview, etc.
  -- we create indexes only for ('r','p')
BEGIN
  -- public.trips
  SELECT c.relkind
    INTO rk
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'trips';

  IF rk IN ('r','p') THEN
    RAISE NOTICE 'public.trips: creating indexes (if not exists)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS trips_loading_region_idx ON public.trips (loading_region)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS trips_unloading_region_idx ON public.trips (unloading_region)';
  ELSIF rk IS NULL THEN
    RAISE NOTICE 'public.trips: not found, skip indexes';
  ELSE
    RAISE NOTICE 'public.trips: relkind=% (not a table), skip indexes', rk;
  END IF;

  -- public.trip_segments
  SELECT c.relkind
    INTO rk
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'trip_segments';

  IF rk IN ('r','p') THEN
    RAISE NOTICE 'public.trip_segments: creating indexes (if not exists)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS trip_segments_loading_region_idx ON public.trip_segments (loading_region)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS trip_segments_unloading_region_idx ON public.trip_segments (unloading_region)';
  ELSIF rk IS NULL THEN
    RAISE NOTICE 'public.trip_segments: not found, skip indexes';
  ELSE
    RAISE NOTICE 'public.trip_segments: relkind=% (not a table), skip indexes', rk;
  END IF;

  -- public.loads
  SELECT c.relkind
    INTO rk
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = 'loads';

  IF rk IN ('r','p') THEN
    RAISE NOTICE 'public.loads: creating indexes (if not exists)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS loads_loading_region_idx ON public.loads (loading_region)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS loads_unloading_region_idx ON public.loads (unloading_region)';
  ELSIF rk IS NULL THEN
    RAISE NOTICE 'public.loads: not found, skip indexes';
  ELSE
    RAISE NOTICE 'public.loads: relkind=% (not a table), skip indexes', rk;
  END IF;
END
$$;

-- 3) Verification (quick signal in logs/psql output; does not fail)
SELECT table_schema, table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('trips','trip_segments','loads')
  AND column_name IN ('loading_region','unloading_region')
ORDER BY table_name, column_name;

-- Optional: restore defaults for the session
RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

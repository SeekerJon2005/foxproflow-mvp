-- FoxProFlow • FixPack • P0 add tr.driver_id to stop driver.alerts.offroute crashes
-- file: scripts/sql/fixpacks/20251223_offroute_add_driver_id_apply.sql
--
-- IMPORTANT:
--   Set REL_TR to the relation aliased as "tr" in tasks_driver_alerts.py SQL (e.g. public.trips or a view).
--   This fixpack only adds a nullable driver_id column (uuid) if missing.
--
-- Rationale:
--   P0 stability: stop periodic task from crashing due to missing column.
--   Semantics of how driver_id should be filled comes later.

\set ON_ERROR_STOP on
\pset pager off

-- >>> CONFIG (edit if needed):
\set REL_TR 'public.trips'
-- <<<

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858410);

DO $$
DECLARE
  rel_tr text := :'REL_TR';
  sch text;
  tbl text;
  exists_rel boolean;
  has_col boolean;
BEGIN
  sch := split_part(rel_tr, '.', 1);
  tbl := split_part(rel_tr, '.', 2);

  SELECT (to_regclass(rel_tr) IS NOT NULL) INTO exists_rel;
  IF NOT exists_rel THEN
    RAISE EXCEPTION 'FAILED: relation % does not exist', rel_tr;
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema=sch AND table_name=tbl AND column_name='driver_id'
  ) INTO has_col;

  IF has_col THEN
    RAISE NOTICE 'P0 offroute: %.driver_id already exists -> no-op', rel_tr;
    RETURN;
  END IF;

  -- Add column as nullable uuid (P0 safe)
  EXECUTE format('ALTER TABLE %s ADD COLUMN driver_id uuid', rel_tr);

  EXECUTE format($c$
    COMMENT ON COLUMN %s.driver_id
    IS 'P0: added to satisfy driver.alerts.offroute query. Nullable. Population logic defined separately.'
  $c$, rel_tr);

  RAISE NOTICE 'P0 offroute: added %.driver_id uuid NULL', rel_tr;
END $$;

-- Optional perf index (safe to add later; keep now as best-effort and non-blocking)
-- NOTE: CONCURRENTLY cannot run inside DO/tx blocks; this is ok because fixpack is executed in psql session.
DO $$
BEGIN
  -- only attempt index if relation is a table (relkind r/p), not a view
  IF EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE (n.nspname||'.'||c.relname)=:'REL_TR'
      AND c.relkind IN ('r','p')
  ) THEN
    BEGIN
      EXECUTE format('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_%s_driver_id ON %s (driver_id)',
                     replace(:'REL_TR','.', '_'), :'REL_TR');
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'P0 offroute: index create skipped: %', SQLERRM;
    END;
  END IF;
END $$;

SELECT pg_advisory_unlock(74858410);

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

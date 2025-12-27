-- FoxProFlow • FixPack • Trips confirmed_at for routing/autoplan ordering
-- file: scripts/sql/fixpacks/20251221_trips_confirmed_at_apply.sql
-- DEVTASK: 353
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--   Unblocks:
--     - routing.enrich.trips ORDER BY COALESCE(t.confirmed_at, t.created_at)
--     - autoplan.confirm which writes confirmed_at
--   Idempotent: safe to run multiple times.

SET lock_timeout = '5s';
SET statement_timeout = '10min';
SET client_min_messages = NOTICE;

-- 1) Ensure core timestamp columns exist (safe for schema drift)
ALTER TABLE IF EXISTS public.trips
  ADD COLUMN IF NOT EXISTS created_at   timestamptz,
  ADD COLUMN IF NOT EXISTS updated_at   timestamptz,
  ADD COLUMN IF NOT EXISTS confirmed_at timestamptz;

-- 2) Defaults + backfill (best-effort; skip cleanly on type mismatch / missing columns)
DO $$
DECLARE
  created_type   text;
  updated_type   text;
  confirmed_type text;
BEGIN
  IF to_regclass('public.trips') IS NULL THEN
    RAISE NOTICE 'public.trips not found, skip';
    RETURN;
  END IF;

  SELECT data_type INTO created_type
    FROM information_schema.columns
   WHERE table_schema='public' AND table_name='trips' AND column_name='created_at';

  SELECT data_type INTO updated_type
    FROM information_schema.columns
   WHERE table_schema='public' AND table_name='trips' AND column_name='updated_at';

  SELECT data_type INTO confirmed_type
    FROM information_schema.columns
   WHERE table_schema='public' AND table_name='trips' AND column_name='confirmed_at';

  -- created_at
  IF created_type ILIKE 'timestamp%' THEN
    BEGIN
      EXECUTE 'ALTER TABLE public.trips ALTER COLUMN created_at SET DEFAULT now()';
    EXCEPTION WHEN datatype_mismatch OR cannot_coerce OR undefined_column THEN
      RAISE NOTICE 'public.trips.created_at: cannot set default (type=%)', created_type;
    END;

    BEGIN
      EXECUTE 'UPDATE public.trips SET created_at = COALESCE(created_at, now()) WHERE created_at IS NULL';
    EXCEPTION WHEN datatype_mismatch OR cannot_coerce OR undefined_column THEN
      RAISE NOTICE 'public.trips.created_at: cannot backfill (type=%)', created_type;
    END;
  ELSE
    RAISE NOTICE 'public.trips.created_at: type=%; skip default/backfill', COALESCE(created_type, '<missing>');
  END IF;

  -- updated_at
  IF updated_type ILIKE 'timestamp%' THEN
    BEGIN
      EXECUTE 'ALTER TABLE public.trips ALTER COLUMN updated_at SET DEFAULT now()';
    EXCEPTION WHEN datatype_mismatch OR cannot_coerce OR undefined_column THEN
      RAISE NOTICE 'public.trips.updated_at: cannot set default (type=%)', updated_type;
    END;

    BEGIN
      EXECUTE 'UPDATE public.trips SET updated_at = COALESCE(updated_at, now()) WHERE updated_at IS NULL';
    EXCEPTION WHEN datatype_mismatch OR cannot_coerce OR undefined_column THEN
      RAISE NOTICE 'public.trips.updated_at: cannot backfill (type=%)', updated_type;
    END;
  ELSE
    RAISE NOTICE 'public.trips.updated_at: type=%; skip default/backfill', COALESCE(updated_type, '<missing>');
  END IF;

  -- confirmed_at: backfill for already confirmed trips (only if status exists)
  IF confirmed_type ILIKE 'timestamp%' THEN
    BEGIN
      EXECUTE $q$
        UPDATE public.trips
           SET confirmed_at = COALESCE(confirmed_at, updated_at, created_at, now())
         WHERE confirmed_at IS NULL
           AND status = 'confirmed'
      $q$;
    EXCEPTION
      WHEN undefined_column THEN
        RAISE NOTICE 'public.trips.status missing, skip confirmed_at backfill';
      WHEN datatype_mismatch OR cannot_coerce THEN
        RAISE NOTICE 'public.trips.confirmed_at/status: type mismatch, skip backfill';
    END;
  ELSE
    RAISE NOTICE 'public.trips.confirmed_at: type=%; skip confirmed_at backfill', COALESCE(confirmed_type, '<missing>');
  END IF;
END
$$;

-- 3) Indexes (best-effort)
DO $$
BEGIN
  IF to_regclass('public.trips') IS NULL THEN
    RETURN;
  END IF;

  BEGIN
    EXECUTE 'CREATE INDEX IF NOT EXISTS trips_confirmed_at_idx ON public.trips(confirmed_at)';
  EXCEPTION WHEN undefined_column THEN
    NULL;
  END;

  BEGIN
    EXECUTE 'CREATE INDEX IF NOT EXISTS trips_created_at_idx ON public.trips(created_at)';
  EXCEPTION WHEN undefined_column THEN
    NULL;
  END;

  BEGIN
    EXECUTE 'CREATE INDEX IF NOT EXISTS trips_updated_at_idx ON public.trips(updated_at)';
  EXCEPTION WHEN undefined_column THEN
    NULL;
  END;
END
$$;

-- 4) Verification (quick signal)
SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_schema='public' AND table_name='trips'
   AND column_name IN ('created_at','updated_at','confirmed_at')
 ORDER BY column_name;

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

-- FoxProFlow • FixPack • Add UUID shadow id for trip_segments without changing existing bigint id
-- file: scripts/sql/fixpacks/20251223_trip_segments_uuid_shadowcol_apply.sql
--
-- Goal:
--   Keep public.trip_segments.id as-is (int8) to avoid breaking dependent views,
--   but provide stable UUID key for worker routing.enrich and future API evolution.
--
-- Adds:
--   - public.ff_uuid_v4() generator (extension-optional)
--   - public.trip_segments.id_uuid uuid NOT NULL DEFAULT ff_uuid_v4()
--   - backfill for existing rows
--   - UNIQUE index on id_uuid (CONCURRENTLY)

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858391);

-- Optional extensions (best-effort)
DO $$
BEGIN
  BEGIN
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS pgcrypto';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgcrypto create skipped: %', SQLERRM;
  END;

  BEGIN
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'uuid-ossp create skipped: %', SQLERRM;
  END;
END $$;

-- UUID generator (no hard dependency on extensions)
CREATE OR REPLACE FUNCTION public.ff_uuid_v4()
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
AS $ff$
DECLARE
  v uuid;
  h text;
  variant_ch text;
BEGIN
  IF to_regprocedure('gen_random_uuid()') IS NOT NULL THEN
    EXECUTE 'SELECT gen_random_uuid()' INTO v;
    RETURN v;
  ELSIF to_regprocedure('uuid_generate_v4()') IS NOT NULL THEN
    EXECUTE 'SELECT uuid_generate_v4()' INTO v;
    RETURN v;
  ELSE
    h := md5(random()::text || clock_timestamp()::text);
    variant_ch := substring('89ab', 1 + floor(random()*4)::int, 1);
    RETURN (
      substring(h,1,8)||'-'||substring(h,9,4)||'-4'||substring(h,13,3)||
      '-'||variant_ch||substring(h,17,3)||
      '-'||substring(h,21,12)
    )::uuid;
  END IF;
END;
$ff$;

DO $$
BEGIN
  IF to_regclass('public.trip_segments') IS NULL THEN
    RAISE NOTICE 'trip_segments.uuid-shadow: public.trip_segments missing -> SKIP';
    RETURN;
  END IF;

  -- Add column if missing
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='trip_segments' AND column_name='id_uuid'
  ) THEN
    EXECUTE 'ALTER TABLE public.trip_segments ADD COLUMN id_uuid uuid';
    EXECUTE 'COMMENT ON COLUMN public.trip_segments.id_uuid IS ''Shadow UUID identifier for worker/API compatibility (do not reuse bigint id).''';
  END IF;

  -- Ensure default
  BEGIN
    EXECUTE 'ALTER TABLE public.trip_segments ALTER COLUMN id_uuid SET DEFAULT public.ff_uuid_v4()';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'trip_segments.uuid-shadow: SET DEFAULT skipped: %', SQLERRM;
  END;

  -- Backfill existing rows
  EXECUTE 'UPDATE public.trip_segments SET id_uuid = public.ff_uuid_v4() WHERE id_uuid IS NULL';

  -- Enforce NOT NULL
  BEGIN
    EXECUTE 'ALTER TABLE public.trip_segments ALTER COLUMN id_uuid SET NOT NULL';
  EXCEPTION WHEN OTHERS THEN
    -- If there are still NULLs (shouldn't), this will fail; keep it loud.
    RAISE EXCEPTION 'trip_segments.uuid-shadow: cannot SET NOT NULL (still nulls?)';
  END;

  RAISE NOTICE 'trip_segments.uuid-shadow: id_uuid ensured (default/backfill/not null).';
END $$;

-- Unique index (must be outside DO; CONCURRENTLY cannot run inside transaction blocks)
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_trip_segments_id_uuid
  ON public.trip_segments (id_uuid);

SELECT pg_advisory_unlock(74858391);

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

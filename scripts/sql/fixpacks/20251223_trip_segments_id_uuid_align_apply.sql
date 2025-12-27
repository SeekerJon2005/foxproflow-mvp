-- FoxProFlow • FixPack • Align public.trip_segments.id to UUID (routing.enrich contract)
-- file: scripts/sql/fixpacks/20251223_trip_segments_id_uuid_align_apply.sql
--
-- Why:
--   worker/tasks/routing.py updates by: WHERE id = %s::uuid
--   If public.trip_segments.id is bigint -> invalid input syntax for type uuid risk.
--
-- Safety gates (must all be true to apply):
--   1) public.trip_segments exists
--   2) column id exists
--   3) base type of id is NOT uuid
--   4) table is empty (rowcount = 0)
--   5) no FK constraints reference public.trip_segments(id)
--
-- Idempotent:
--   - If already uuid (or domain over uuid): no-op
--   - If unsafe: SKIP with NOTICE

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858390);

-- Best-effort extensions (optional)
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

-- UUID v4 generator with runtime dispatch (no hard dependency on extensions at CREATE time)
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
    -- fallback without extensions: format md5 into RFC4122-ish v4 uuid
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

-- Main guarded alteration
DO $$
DECLARE
  id_udt     text;
  base_type  text;
  rows_cnt   bigint;
  fk_refs    int;
  id_attnum  int;
BEGIN
  IF to_regclass('public.trip_segments') IS NULL THEN
    RAISE NOTICE 'trip_segments.id uuid-align: public.trip_segments missing -> SKIP';
    RETURN;
  END IF;

  -- Determine base type (domain-safe): uuid OR domain over uuid is acceptable
  SELECT
    c.udt_name,
    (CASE WHEN t.typtype = 'd' THEN bt.typname ELSE t.typname END) AS base_type
  INTO id_udt, base_type
  FROM information_schema.columns c
  JOIN pg_class cl ON cl.oid = 'public.trip_segments'::regclass
  JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attname = 'id' AND a.attnum > 0 AND NOT a.attisdropped
  JOIN pg_type t ON t.oid = a.atttypid
  LEFT JOIN pg_type bt ON bt.oid = t.typbasetype
  WHERE c.table_schema='public' AND c.table_name='trip_segments' AND c.column_name='id';

  IF id_udt IS NULL THEN
    RAISE NOTICE 'trip_segments.id uuid-align: column public.trip_segments.id missing -> SKIP';
    RETURN;
  END IF;

  IF base_type = 'uuid' THEN
    RAISE NOTICE 'trip_segments.id uuid-align: already uuid (or domain over uuid) -> OK (no-op)';
    RETURN;
  END IF;

  EXECUTE 'SELECT count(*) FROM public.trip_segments' INTO rows_cnt;

  SELECT a.attnum INTO id_attnum
  FROM pg_attribute a
  WHERE a.attrelid='public.trip_segments'::regclass
    AND a.attname='id'
    AND a.attnum > 0
    AND NOT a.attisdropped;

  IF id_attnum IS NULL THEN
    RAISE NOTICE 'trip_segments.id uuid-align: cannot resolve attnum for id -> SKIP';
    RETURN;
  END IF;

  SELECT count(*) INTO fk_refs
  FROM pg_constraint con
  WHERE con.contype='f'
    AND con.confrelid='public.trip_segments'::regclass
    AND id_attnum = ANY(con.confkey);

  IF rows_cnt <> 0 THEN
    RAISE NOTICE 'trip_segments.id uuid-align: trip_segments has % rows -> SKIP (needs data migration plan)', rows_cnt;
    RETURN;
  END IF;

  IF fk_refs <> 0 THEN
    RAISE NOTICE 'trip_segments.id uuid-align: found % FK(s) referencing public.trip_segments(id) -> SKIP', fk_refs;
    RETURN;
  END IF;

  -- Detach any serial default if present (safe)
  BEGIN
    EXECUTE 'ALTER TABLE public.trip_segments ALTER COLUMN id DROP DEFAULT';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'trip_segments.id uuid-align: DROP DEFAULT skipped: %', SQLERRM;
  END;

  -- Convert type (table is empty -> safe)
  EXECUTE 'ALTER TABLE public.trip_segments ALTER COLUMN id TYPE uuid USING public.ff_uuid_v4()';
  EXECUTE 'ALTER TABLE public.trip_segments ALTER COLUMN id SET DEFAULT public.ff_uuid_v4()';

  -- Make identifier not-null (safe when table empty)
  EXECUTE 'ALTER TABLE public.trip_segments ALTER COLUMN id SET NOT NULL';

  EXECUTE $c$
    COMMENT ON COLUMN public.trip_segments.id
    IS 'Segment identifier (uuid). Required by routing.enrich update-by-id (casts to ::uuid).'
  $c$;

  RAISE NOTICE 'trip_segments.id uuid-align: ALTERED public.trip_segments.id to uuid (table empty, no FK refs).';
END $$;

SELECT pg_advisory_unlock(74858390);

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

-- FoxProFlow • Verify/Smoke • P0 offroute tr.driver_id exists
-- file: scripts/sql/verify/20251223_offroute_add_driver_id_smoke.sql

\set ON_ERROR_STOP on
\pset pager off

-- >>> CONFIG (edit if needed):
\set REL_TR 'public.trips'
-- <<<

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

DO $$
DECLARE
  rel_tr text := :'REL_TR';
  sch text := split_part(rel_tr,'.',1);
  tbl text := split_part(rel_tr,'.',2);
  ok boolean;
  udt text;
BEGIN
  IF to_regclass(rel_tr) IS NULL THEN
    RAISE EXCEPTION 'FAILED: relation % missing', rel_tr;
  END IF;

  SELECT c.udt_name INTO udt
  FROM information_schema.columns c
  WHERE c.table_schema=sch AND c.table_name=tbl AND c.column_name='driver_id';

  IF udt IS NULL THEN
    RAISE EXCEPTION 'FAILED: %.driver_id missing', rel_tr;
  END IF;

  IF udt <> 'uuid' THEN
    RAISE EXCEPTION 'FAILED: %.driver_id expected uuid, got %', rel_tr, udt;
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema=sch AND table_name=tbl AND column_name='driver_id'
  ) INTO ok;

  IF NOT ok THEN
    RAISE EXCEPTION 'FAILED: %.driver_id still not found after apply', rel_tr;
  END IF;
END $$;

-- smoke query that matches the failing projection style
-- (will not error if column exists)
EXECUTE format('SELECT tr.driver_id AS driver_id FROM %s tr LIMIT 1', :'REL_TR');

SELECT 'PASS: P0 offroute tr.driver_id exists' AS pass;

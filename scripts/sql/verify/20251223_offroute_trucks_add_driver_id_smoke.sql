-- FoxProFlow • Verify/Smoke • P0 offroute trucks.driver_id exists
-- file: scripts/sql/verify/20251223_offroute_trucks_add_driver_id_smoke.sql

\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

DO $$
DECLARE
  udt text;
BEGIN
  IF to_regclass('public.trucks') IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trucks';
  END IF;

  SELECT c.udt_name INTO udt
  FROM information_schema.columns c
  WHERE c.table_schema='public' AND c.table_name='trucks' AND c.column_name='driver_id';

  IF udt IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trucks.driver_id';
  END IF;

  IF udt <> 'uuid' THEN
    RAISE EXCEPTION 'FAILED: public.trucks.driver_id expected uuid, got %', udt;
  END IF;
END $$;

-- smoke projection exactly like failing query
SELECT tr.driver_id AS driver_id
FROM public.trucks tr
LIMIT 1;

SELECT 'PASS: P0 offroute public.trucks.driver_id exists' AS pass;

-- FoxProFlow • Verify/Smoke • P0 trips.completed_at exists
-- file: scripts/sql/verify/20251223_trips_add_completed_at_smoke.sql

\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

DO $$
DECLARE udt text;
BEGIN
  IF to_regclass('public.trips') IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trips';
  END IF;

  SELECT c.udt_name INTO udt
  FROM information_schema.columns c
  WHERE c.table_schema='public' AND c.table_name='trips' AND c.column_name='completed_at';

  IF udt IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trips.completed_at';
  END IF;

  IF udt <> 'timestamptz' THEN
    RAISE EXCEPTION 'FAILED: public.trips.completed_at expected timestamptz, got %', udt;
  END IF;
END $$;

-- smoke: query fragment compiles
SELECT count(*) AS active_cnt
FROM public.trips t
WHERE t.completed_at IS NULL;

SELECT 'PASS: P0 public.trips.completed_at exists' AS pass;

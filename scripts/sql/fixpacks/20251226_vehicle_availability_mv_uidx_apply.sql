-- FoxProFlow • FixPack
-- file: scripts/sql/fixpacks/20251226_vehicle_availability_mv_uidx_apply.sql
-- lane: C-SQL / DATA / CONTRACTS
-- owner: Архитектор Яцков Евгений Анатольевич
--
-- Goal:
--   Make public.vehicle_availability_mv safe for REFRESH ... CONCURRENTLY
--   by ensuring a UNIQUE, valid, ready, non-partial index exists.
--
-- Strategy:
--   Enforce uniqueness on (truck_id). One availability row per truck.

\pset pager off
\set ON_ERROR_STOP on

SELECT pg_advisory_lock(hashtext('ff:fixpack:vehicle_availability_mv_uidx')::bigint);

DO $$
DECLARE
  mv regclass;
  is_pop boolean;
  null_cnt int;
  dup_cnt  int;
BEGIN
  mv := to_regclass('public.vehicle_availability_mv');
  IF mv IS NULL THEN
    RAISE EXCEPTION 'MISSING: public.vehicle_availability_mv';
  END IF;

  -- If not populated -> first refresh (NON-concurrently is allowed in txn)
  SELECT ispopulated INTO is_pop
    FROM pg_matviews
   WHERE schemaname='public' AND matviewname='vehicle_availability_mv';

  IF is_pop IS DISTINCT FROM true THEN
    RAISE NOTICE 'INFO: vehicle_availability_mv is not populated, refreshing (non-concurrently)';
    EXECUTE 'REFRESH MATERIALIZED VIEW public.vehicle_availability_mv';
    EXECUTE 'ANALYZE public.vehicle_availability_mv';
  END IF;

  -- Hard safety: truck_id must be NOT NULL for uniqueness to be meaningful
  EXECUTE 'SELECT count(*) FROM public.vehicle_availability_mv WHERE truck_id IS NULL' INTO null_cnt;
  IF null_cnt > 0 THEN
    RAISE EXCEPTION 'NOT_CONCURRENT_READY: public.vehicle_availability_mv has % rows with NULL truck_id', null_cnt;
  END IF;

  -- Hard safety: ensure one row per truck_id
  EXECUTE $q$
    SELECT count(*) FROM (
      SELECT truck_id
        FROM public.vehicle_availability_mv
       GROUP BY 1
      HAVING count(*) > 1
    ) d
  $q$ INTO dup_cnt;

  IF dup_cnt > 0 THEN
    RAISE EXCEPTION 'NOT_CONCURRENT_READY: public.vehicle_availability_mv has duplicate truck_id groups=%', dup_cnt;
  END IF;

END $$;

-- Create UNIQUE index concurrently (must be outside a transaction block; script has no BEGIN)
-- Note: IF NOT EXISTS checks by name; this is deliberate.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_vehicle_availability_mv_truck_id
  ON public.vehicle_availability_mv USING btree (truck_id);

ANALYZE public.vehicle_availability_mv;

SELECT pg_advisory_unlock(hashtext('ff:fixpack:vehicle_availability_mv_uidx')::bigint);

SELECT 'OK: ensured UNIQUE index for public.vehicle_availability_mv (truck_id)' AS _;

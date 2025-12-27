-- FoxProFlow • FixPack • P0 add public.trucks.driver_id (uuid) for driver.alerts.offroute
-- file: scripts/sql/fixpacks/20251223_offroute_trucks_add_driver_id_apply.sql
--
-- Symptom:
--   driver.alerts.offroute query uses JOIN public.trucks tr ... tr.driver_id
--   but column public.trucks.driver_id does not exist.
--
-- P0 Goal:
--   Stop periodic task crashes. Add nullable uuid column.
--   Population semantics (how driver is assigned to truck) handled separately.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858411);

DO $$
BEGIN
  IF to_regclass('public.trucks') IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trucks';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='trucks' AND column_name='driver_id'
  ) THEN
    RAISE NOTICE 'P0 offroute: public.trucks.driver_id already exists -> no-op';
    RETURN;
  END IF;

  ALTER TABLE public.trucks ADD COLUMN driver_id uuid NULL;

  COMMENT ON COLUMN public.trucks.driver_id
    IS 'P0: driver assigned to truck (uuid). Added to satisfy driver.alerts.offroute query. Nullable; population logic defined separately.';

  RAISE NOTICE 'P0 offroute: added public.trucks.driver_id uuid NULL';
END $$;

-- Optional index (non-blocking)
DO $$
BEGIN
  BEGIN
    EXECUTE 'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_trucks_driver_id ON public.trucks (driver_id)';
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'P0 offroute: index create skipped: %', SQLERRM;
  END;
END $$;

SELECT pg_advisory_unlock(74858411);

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

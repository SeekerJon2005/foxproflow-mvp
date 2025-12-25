-- FoxProFlow • FixPack • P0 add public.trips.completed_at for driver.alerts.offroute
-- file: scripts/sql/fixpacks/20251223_trips_add_completed_at_apply.sql
--
-- Symptom:
--   tasks_driver_alerts.py filters: (t.completed_at IS NULL)
--   but public.trips.completed_at does not exist.
--
-- P0 Goal:
--   Stop periodic task crash. Add nullable timestamptz column.

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858412);

DO $$
BEGIN
  IF to_regclass('public.trips') IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trips';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='trips' AND column_name='completed_at'
  ) THEN
    RAISE NOTICE 'P0 offroute: public.trips.completed_at already exists -> no-op';
    RETURN;
  END IF;

  ALTER TABLE public.trips ADD COLUMN completed_at timestamptz NULL;

  COMMENT ON COLUMN public.trips.completed_at
    IS 'Trip completion timestamp (NULL = active). Added for driver.alerts.offroute filter.';

  RAISE NOTICE 'P0 offroute: added public.trips.completed_at timestamptz NULL';
END $$;

SELECT pg_advisory_unlock(74858412);

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

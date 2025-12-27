-- FoxProFlow • FixPack • Add updated_at trigger for public.trip_segments
-- file: scripts/sql/fixpacks/20251224_trip_segments_updated_at_trigger_apply.sql

\set ON_ERROR_STOP on
\pset pager off

SET lock_timeout = '10s';
SET statement_timeout = '15min';
SET client_min_messages = warning;

SELECT pg_advisory_lock(74858440);

CREATE OR REPLACE FUNCTION public.ff_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DO $$
BEGIN
  IF to_regclass('public.trip_segments') IS NULL THEN
    RAISE NOTICE 'trip_segments.updated_at trigger: public.trip_segments missing -> SKIP';
    RETURN;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger tr
    WHERE tr.tgrelid = 'public.trip_segments'::regclass
      AND tr.tgname = 'trg_trip_segments_set_updated_at'
  ) THEN
    EXECUTE '
      CREATE TRIGGER trg_trip_segments_set_updated_at
      BEFORE UPDATE ON public.trip_segments
      FOR EACH ROW
      EXECUTE FUNCTION public.ff_set_updated_at()
    ';
    RAISE NOTICE 'trip_segments.updated_at trigger: created';
  ELSE
    RAISE NOTICE 'trip_segments.updated_at trigger: already exists';
  END IF;
END $$;

SELECT pg_advisory_unlock(74858440);

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

-- FoxProFlow • Verify/Smoke • updated_at trigger on public.trip_segments
-- file: scripts/sql/verify/20251224_trip_segments_updated_at_trigger_smoke.sql

\set ON_ERROR_STOP on
\pset pager off

DO $$
DECLARE
  v_uuid uuid;
  t0 timestamptz;
  t1 timestamptz;
BEGIN
  IF to_regclass('public.trip_segments') IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing public.trip_segments';
  END IF;

  SELECT id_uuid INTO v_uuid
  FROM public.trip_segments
  ORDER BY id DESC
  LIMIT 1;

  IF v_uuid IS NULL THEN
    RAISE NOTICE 'SKIP: no trip_segments rows to test';
    RETURN;
  END IF;

  SELECT updated_at INTO t0 FROM public.trip_segments WHERE id_uuid = v_uuid;

  UPDATE public.trip_segments
  SET meta = meta || jsonb_build_object('smoke_updated_at', now()::text)
  WHERE id_uuid = v_uuid;

  SELECT updated_at INTO t1 FROM public.trip_segments WHERE id_uuid = v_uuid;

  IF t1 IS NULL OR t0 IS NULL OR t1 <= t0 THEN
    RAISE EXCEPTION 'FAILED: updated_at did not advance (t0=%, t1=%)', t0, t1;
  END IF;
END $$;

SELECT 'PASS: trip_segments.updated_at trigger ok' AS pass;

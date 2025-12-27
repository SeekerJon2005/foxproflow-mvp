-- FoxProFlow • FixPack • Trip segments routing metric columns
-- file: scripts/sql/fixpacks/20251221_trip_segments_routing_metrics_apply.sql
-- DEVTASK: 351
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
--   Unblocks routing.enrich.trips (expects road_km/drive_sec; optionally segment_order).
--   Idempotent: safe to run multiple times.

SET lock_timeout = '5s';
SET statement_timeout = '10min';
SET client_min_messages = NOTICE;

-- Replace DEVTASK line above with your real DevTask id.

ALTER TABLE IF EXISTS public.trip_segments
  ADD COLUMN IF NOT EXISTS road_km double precision,
  ADD COLUMN IF NOT EXISTS drive_sec integer,
  ADD COLUMN IF NOT EXISTS route_polyline text,
  ADD COLUMN IF NOT EXISTS polyline text;

-- Optional: keep schema drift down (used for ordering/debug; safe to be nullable).
ALTER TABLE IF EXISTS public.trip_segments
  ADD COLUMN IF NOT EXISTS segment_order integer;

-- Best-effort normalize segment_order (dev-friendly; safe if table is small).
DO $$
BEGIN
  IF to_regclass('public.trip_segments') IS NOT NULL THEN
    -- If segment_order is NULL, set to 1 (baseline)
    EXECUTE 'UPDATE public.trip_segments SET segment_order = 1 WHERE segment_order IS NULL';
  END IF;
END
$$;

-- Helpful index for stable ordering per trip (optional, cheap)
DO $$
BEGIN
  IF to_regclass('public.trip_segments') IS NOT NULL THEN
    BEGIN
      EXECUTE 'CREATE INDEX IF NOT EXISTS trip_segments_trip_id_segment_order_idx ON public.trip_segments(trip_id, segment_order)';
    EXCEPTION WHEN undefined_column THEN
      -- trip_id might not exist in some drifted schemas; ignore
      RAISE NOTICE 'trip_segments: trip_id missing, skip index';
    END;
  END IF;
END
$$;

RESET client_min_messages;
RESET statement_timeout;
RESET lock_timeout;

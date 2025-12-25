BEGIN;

ALTER TABLE IF EXISTS public.trip_segments
  ADD COLUMN IF NOT EXISTS road_km numeric(10,3),
  ADD COLUMN IF NOT EXISTS drive_sec integer,
  ADD COLUMN IF NOT EXISTS route_polyline text;

CREATE TABLE IF NOT EXISTS public.route_cache (
  od_hash     text PRIMARY KEY,
  backend     text NOT NULL,
  distance_m  numeric NOT NULL,
  duration_s  numeric NOT NULL,
  polyline    text,
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS route_cache_updated_at_idx ON public.route_cache(updated_at DESC);

COMMENT ON COLUMN public.trip_segments.road_km        IS 'Длина плеча по дорогам, км';
COMMENT ON COLUMN public.trip_segments.drive_sec      IS 'Время в пути по дорогам, сек';
COMMENT ON COLUMN public.trip_segments.route_polyline IS 'Polyline6 (OSRM) или shape (Valhalla)';

COMMIT;

BEGIN;

ALTER TABLE public.trip_segments
    ADD COLUMN IF NOT EXISTS route_polyline text;

COMMENT ON COLUMN public.trip_segments.route_polyline IS
    'Закодированный polyline маршрута по сегменту (OSRM, encoded polyline)';

COMMIT;

BEGIN;

ALTER TABLE public.trip_segments
    ADD COLUMN IF NOT EXISTS polyline text;

COMMENT ON COLUMN public.trip_segments.polyline IS
    'Легаси-поле polyline для совместимости со старым кодом (используется как fallback к route_polyline).';

COMMIT;

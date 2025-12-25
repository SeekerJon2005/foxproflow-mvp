BEGIN;

ALTER TABLE public.trip_segments
    ADD COLUMN IF NOT EXISTS road_km   numeric,
    ADD COLUMN IF NOT EXISTS drive_sec integer;

COMMENT ON COLUMN public.trip_segments.road_km IS
    'Длина сегмента по дороге, км (OSRM)';
COMMENT ON COLUMN public.trip_segments.drive_sec IS
    'Время движения по сегменту, сек (OSRM)';

COMMIT;

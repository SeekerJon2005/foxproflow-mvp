BEGIN;

ALTER TABLE public.city_map
    ADD COLUMN IF NOT EXISTS source text;

COMMENT ON COLUMN public.city_map.source IS
    'Источник записи (manual/import/geocoder и т.п.), legacy для geo-скриптов.';

COMMIT;

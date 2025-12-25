BEGIN;

ALTER TABLE public.city_map
    ADD COLUMN IF NOT EXISTS region text;

COMMENT ON COLUMN public.city_map.region IS
    'Человекочитаемое наименование региона (legacy-совместимость с geo-скриптами).';

COMMIT;

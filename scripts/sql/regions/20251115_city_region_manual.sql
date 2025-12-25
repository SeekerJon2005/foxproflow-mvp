-- 2025-11-15 — FoxProFlow
-- Справочник ручной нормализации город/регион → канонический код региона.

CREATE TABLE IF NOT EXISTS public.city_region_manual (
    id              bigserial PRIMARY KEY,
    raw_city        text,
    raw_region      text,
    region_code     text,        -- канонический код (например, RU-MOW, RU-NVS)
    source          text,        -- откуда взялась пара (например, 'trips_ru_unk'),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Индекс для быстрых join'ов по сырым значениям
CREATE INDEX IF NOT EXISTS city_region_manual_raw_idx
    ON public.city_region_manual (raw_city, raw_region);

-- Триггер на updated_at
CREATE OR REPLACE FUNCTION public.fn_city_region_manual_touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $func$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$func$;

DROP TRIGGER IF EXISTS trg_city_region_manual_touch_updated_at
ON public.city_region_manual;

CREATE TRIGGER trg_city_region_manual_touch_updated_at
BEFORE UPDATE ON public.city_region_manual
FOR EACH ROW
EXECUTE FUNCTION public.fn_city_region_manual_touch_updated_at();

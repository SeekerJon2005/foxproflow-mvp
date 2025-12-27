-- 2025-11-20  OD distance cache: таблица + upsert-функция
CREATE TABLE IF NOT EXISTS public.od_distance_cache (
    id            bigserial PRIMARY KEY,
    lat1          double precision,
    lon1          double precision,
    lat2          double precision,
    lon2          double precision,
    city1         text,
    city2         text,
    distance_km   double precision,
    profile       integer,
    source        text,
    precision_km  smallint,
    updated_at    timestamptz DEFAULT now()
);

-- Гарантируем, что нужные колонки есть (если таблица уже существовала)
ALTER TABLE public.od_distance_cache
    ADD COLUMN IF NOT EXISTS lat1         double precision,
    ADD COLUMN IF NOT EXISTS lon1         double precision,
    ADD COLUMN IF NOT EXISTS lat2         double precision,
    ADD COLUMN IF NOT EXISTS lon2         double precision,
    ADD COLUMN IF NOT EXISTS city1        text,
    ADD COLUMN IF NOT EXISTS city2        text,
    ADD COLUMN IF NOT EXISTS distance_km  double precision,
    ADD COLUMN IF NOT EXISTS profile      integer,
    ADD COLUMN IF NOT EXISTS source       text,
    ADD COLUMN IF NOT EXISTS precision_km smallint,
    ADD COLUMN IF NOT EXISTS updated_at   timestamptz DEFAULT now();

-- Уникальность по гео+профилю+точности
CREATE UNIQUE INDEX IF NOT EXISTS idx_od_distance_cache_unique
    ON public.od_distance_cache (lat1, lon1, lat2, lon2, profile, precision_km);

-- Быстрый поиск по городам (если нужны будут city-based запросы)
CREATE INDEX IF NOT EXISTS idx_od_distance_cache_city
    ON public.od_distance_cache (city1, city2);

-- Функция upsert для OD-кэша.
-- Сигнатура подобрана под реальные вызовы из логов:
--   (double precision, double precision, double precision, double precision,
--    text, text, double precision, integer, text, smallint)
CREATE OR REPLACE FUNCTION public.fn_od_distance_cache_upsert(
    p_lat1         double precision,
    p_lon1         double precision,
    p_lat2         double precision,
    p_lon2         double precision,
    p_city1        text,
    p_city2        text,
    p_distance_km  double precision,
    p_profile      integer,
    p_source       text,
    p_precision_km smallint
)
RETURNS boolean
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.od_distance_cache (
        lat1, lon1,
        lat2, lon2,
        city1, city2,
        distance_km,
        profile,
        source,
        precision_km,
        updated_at
    )
    VALUES (
        p_lat1, p_lon1,
        p_lat2, p_lon2,
        p_city1, p_city2,
        p_distance_km,
        p_profile,
        p_source,
        p_precision_km,
        now()
    )
    ON CONFLICT (lat1, lon1, lat2, lon2, profile, precision_km)
    DO UPDATE
    SET
        city1       = COALESCE(EXCLUDED.city1, public.od_distance_cache.city1),
        city2       = COALESCE(EXCLUDED.city2, public.od_distance_cache.city2),
        distance_km = EXCLUDED.distance_km,
        source      = COALESCE(EXCLUDED.source, public.od_distance_cache.source),
        updated_at  = now();

    RETURN true;
END;
$$;

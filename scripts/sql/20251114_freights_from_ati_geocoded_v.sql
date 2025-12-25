-- 20251114_freights_from_ati_geocoded_v.sql
-- Геокодированная витрина ATI-грузов:
--   freights_from_ati_v + city_map → координаты и регион погрузки/выгрузки.
--
-- Требования к схеме:
--   • public.freights_from_ati_v      — плоский слой (см. 20251114_freights_from_ati_v.sql)
--   • public.city_map(name, region, lat, lon) — справочник городов с координатами
--
-- Скрипт:
--   • не падает, если базовой вьюхи/таблицы ещё нет (даёт NOTICE и выходим);
--   • если city_map отсутствует, создаёт витрину с NULL-координатами (fallback).

DO $$
DECLARE
  has_base boolean;
  has_city boolean;
BEGIN
  -- 0) Проверяем, что базовая витрина существует
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.views
    WHERE table_schema = 'public'
      AND table_name   = 'freights_from_ati_v'
  )
  INTO has_base;

  IF NOT has_base THEN
    RAISE NOTICE 'View public.freights_from_ati_v not found, skipping freights_from_ati_geocoded_v migration';
    RETURN;
  END IF;

  -- 1) Проверяем наличие справочника city_map
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name   = 'city_map'
  )
  INTO has_city;

  IF NOT has_city THEN
    -- Fallback-вариант без геоданных: оставляем поля, но заполняем NULL
    EXECUTE $view_fallback$
      CREATE OR REPLACE VIEW public.freights_from_ati_geocoded_v AS
      SELECT
        f.*,
        NULL::text   AS loading_place_name,
        NULL::text   AS loading_region,
        NULL::float8 AS loading_lat,
        NULL::float8 AS loading_lon,
        NULL::text   AS unloading_place_name,
        NULL::text   AS unloading_region,
        NULL::float8 AS unloading_lat,
        NULL::float8 AS unloading_lon
      FROM public.freights_from_ati_v AS f;
    $view_fallback$;

    RAISE NOTICE 'Table public.city_map not found, created freights_from_ati_geocoded_v with NULL geodata';
  ELSE
    -- Нормальный вариант: JOIN на city_map по упрощённым ключам места
    EXECUTE $view_main$
      CREATE OR REPLACE VIEW public.freights_from_ati_geocoded_v AS
      SELECT
        f.src,
        f.external_id,
        f.parsed_at,
        f.raw_id,
        f.title_raw,
        f.loading_raw,
        f.unloading_raw,
        f.loading_place_key,
        f.unloading_place_key,
        f.price_raw,
        f.price_rub,
        f.distance_km,
        f.weight_tons,
        f.volume_m3,
        f.loading_date_raw,
        f.loading_date_norm,

        cm_load.name   AS loading_place_name,
        cm_load.region AS loading_region,
        cm_load.lat    AS loading_lat,
        cm_load.lon    AS loading_lon,

        cm_unload.name   AS unloading_place_name,
        cm_unload.region AS unloading_region,
        cm_unload.lat    AS unloading_lat,
        cm_unload.lon    AS unloading_lon

      FROM public.freights_from_ati_v AS f
      LEFT JOIN public.city_map AS cm_load
        ON cm_load.name = f.loading_place_key
      LEFT JOIN public.city_map AS cm_unload
        ON cm_unload.name = f.unloading_place_key;
    $view_main$;
  END IF;

  -- 2) Комментарии к витрине/колонкам (общие для обоих вариантов)
  EXECUTE $cmt$
    COMMENT ON VIEW public.freights_from_ati_geocoded_v IS
      'ATI freights flattened and geocoded via city_map; base for ETL into public.freights.';

    COMMENT ON COLUMN public.freights_from_ati_geocoded_v.loading_place_name IS
      'Matched loading place name from city_map (may be NULL when not found).';

    COMMENT ON COLUMN public.freights_from_ati_geocoded_v.loading_region IS
      'Region code for loading place from city_map.region (e.g. RU-MOW), may be NULL.';

    COMMENT ON COLUMN public.freights_from_ati_geocoded_v.loading_lat IS
      'Latitude of loading place from city_map.lat (WGS84), may be NULL.';

    COMMENT ON COLUMN public.freights_from_ati_geocoded_v.loading_lon IS
      'Longitude of loading place from city_map.lon (WGS84), may be NULL.';

    COMMENT ON COLUMN public.freights_from_ati_geocoded_v.unloading_place_name IS
      'Matched unloading place name from city_map (may be NULL).';

    COMMENT ON COLUMN public.freights_from_ati_geocoded_v.unloading_region IS
      'Region code for unloading place from city_map.region, may be NULL.';

    COMMENT ON COLUMN public.freights_from_ati_geocoded_v.unloading_lat IS
      'Latitude of unloading place from city_map.lat (WGS84), may be NULL.';

    COMMENT ON COLUMN public.freights_from_ati_geocoded_v.unloading_lon IS
      'Longitude of unloading place from city_map.lon (WGS84), may be NULL.';
  $cmt$;

END $$;

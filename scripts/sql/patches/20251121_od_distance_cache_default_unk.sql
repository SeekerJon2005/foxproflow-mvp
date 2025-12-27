-- 2025-11-21
-- Patch: установить дефолтные значения для origin_region/dest_region в od_distance_cache.
-- Цель: перестать падать на NOT NULL при upsert из fn_od_distance_cache_upsert,
--       пока функция не заполняет регионы явно.
-- NDC: не меняет уже существующие строки, только добавляет DEFAULT к колонкам.
-- NOTE: origin_region/dest_region по умолчанию = 'RU-UNK' для кеша lat/lon.
--       Корректные регионы должны в дальнейшем дообогащаться отдельным процессом
--       (например, через city_map / geo-enrichment-агента), а не внутри upsert-функции.

ALTER TABLE public.od_distance_cache
  ALTER COLUMN origin_region SET DEFAULT 'RU-UNK',
  ALTER COLUMN dest_region   SET DEFAULT 'RU-UNK';

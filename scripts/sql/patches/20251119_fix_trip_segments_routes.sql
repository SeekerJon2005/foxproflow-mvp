-- file: scripts/sql/patches/20251119_fix_trip_segments_routes.sql
--
-- Назначение:
--   1) Для рейсов в trips_recent_clean_v без маршрута (road_km/drive_sec IS NULL),
--      у которых НЕТ ни одного сегмента, добавить базовый сегмент
--      по origin_region/dest_region + price_rub.
--   2) Для сегментов с NULL-координатами — подтянуть lat/lon из region_centroids
--      (по коду ИЛИ по имени региона, без учёта регистра).
--
-- Недеструктивно, идемпотентно:
--   • INSERT только там, где trip_segments.s.trip_id IS NULL;
--   • UPDATE только для сегментов с NULL src_lat/dst_lat;
--   • основан на trips_recent_clean_v, поэтому работает только по «видимым» рейсам.

BEGIN;

-------------------------------
-- 1. Добавляем отсутствующие сегменты
-------------------------------
WITH missing_seg AS (
  SELECT
    v.id                AS trip_id,
    v.origin_region     AS o,
    v.dest_region       AS d,
    COALESCE(v.price_rub, 0)::numeric AS price_rub
  FROM public.trips_recent_clean_v v
  LEFT JOIN public.trip_segments s
         ON s.trip_id = v.id
  WHERE (v.road_km IS NULL OR v.drive_sec IS NULL)
    AND s.trip_id IS NULL
)
INSERT INTO public.trip_segments (
  trip_id,
  segment_order,
  origin_region,
  dest_region,
  src_lat,
  src_lon,
  dst_lat,
  dst_lon,
  price_rub
)
SELECT
  m.trip_id,
  1,
  m.o,
  m.d,
  o.lat,
  o.lon,
  d.lat,
  d.lon,
  m.price_rub
FROM missing_seg m
LEFT JOIN public.region_centroids o
  ON o.code = m.o
  OR lower(o.name) = lower(m.o)
LEFT JOIN public.region_centroids d
  ON d.code = m.d
  OR lower(d.name) = lower(m.d);

-------------------------------
-- 2. Добиваем координаты сегментов, где они NULL
-------------------------------
UPDATE public.trip_segments s
SET
  src_lat = o.lat,
  src_lon = o.lon,
  dst_lat = d.lat,
  dst_lon = d.lon
FROM public.region_centroids o,
     public.region_centroids d
WHERE s.trip_id IN (
    SELECT id
    FROM public.trips_recent_clean_v
    WHERE road_km IS NULL
       OR drive_sec IS NULL
)
  AND (s.src_lat IS NULL OR s.dst_lat IS NULL)
  AND (
        o.code = s.origin_region
     OR lower(o.name) = lower(s.origin_region)
  )
  AND (
        d.code = s.dest_region
     OR lower(d.name) = lower(s.dest_region)
  );

COMMIT;

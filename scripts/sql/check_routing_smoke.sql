-- scripts/sql/check_routing_smoke.sql
-- Быстрый smoke-тест покрытия routing/OSRM и витрины trips_recent_v.

-- 1. Статистика по сегментам рейсов (trip_segments):
SELECT
  count(*)                                      AS seg_total,
  count(*) FILTER (WHERE road_km IS NOT NULL)   AS seg_with_road,
  count(*) FILTER (WHERE road_km IS NULL)       AS seg_without_road
FROM public.trip_segments;

-- 2. Распределение дистанций/времени среди сегментов с рассчитанным маршрутом:
SELECT
  count(*)                                      AS seg_with_road,
  min(road_km)                                  AS road_km_min,
  max(road_km)                                  AS road_km_max,
  percentile_disc(0.50) WITHIN GROUP (ORDER BY road_km) AS road_km_p50,
  percentile_disc(0.90) WITHIN GROUP (ORDER BY road_km) AS road_km_p90,
  min(drive_sec)                                AS drive_sec_min,
  max(drive_sec)                                AS drive_sec_max,
  percentile_disc(0.50) WITHIN GROUP (ORDER BY drive_sec) AS drive_sec_p50,
  percentile_disc(0.90) WITHIN GROUP (ORDER BY drive_sec) AS drive_sec_p90
FROM public.trip_segments
WHERE road_km IS NOT NULL;

-- 3. Связка подтверждённых рейсов и сегментов:
WITH confirmed AS (
    SELECT id
    FROM public.trips
    WHERE status = 'confirmed'
)
SELECT
    (SELECT count(*) FROM confirmed) AS trips_confirmed,

    (SELECT count(DISTINCT ts.trip_id)
     FROM confirmed c
     JOIN public.trip_segments ts
       ON ts.trip_id = c.id)        AS trips_with_segments,

    (SELECT count(*)
     FROM confirmed c
     WHERE NOT EXISTS (
         SELECT 1
         FROM public.trip_segments ts
         WHERE ts.trip_id = c.id
     ))                             AS trips_without_segments;

-- 4. Качество витрины trips_recent_v:
--    origin/dest всегда должны быть заполнены, road_km может быть NULL,
--    если маршрут ещё не посчитан.
SELECT
  count(*)                                           AS total_rows,
  count(*) FILTER (WHERE origin_region IS NULL)      AS no_origin,
  count(*) FILTER (WHERE dest_region   IS NULL)      AS no_dest,
  count(*) FILTER (WHERE road_km      IS NULL)       AS no_road_km,
  count(*) FILTER (WHERE road_km      IS NOT NULL)   AS with_road_km
FROM public.trips_recent_v;

-- 5. Быстрый срез последних N рейсов из витрины (для визуальной проверки):
SELECT
  id,
  status,
  created_at,
  confirmed_at,
  origin_region,
  dest_region,
  price_rub,
  road_km,
  drive_sec
FROM public.trips_recent_v
ORDER BY created_at DESC
LIMIT 20;

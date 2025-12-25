
-- file: scripts/sql/20251110_ops_missing_scan.sql
CREATE SCHEMA IF NOT EXISTS ops;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- confirmed-трипы без road_km
CREATE OR REPLACE VIEW ops.missing_trips_no_km_v AS
SELECT t.id,
       t.truck_id,
       t.meta->'autoplan'->>'origin_region' AS origin_region,
       t.meta->'autoplan'->>'dest_region'   AS dest_region,
       t.meta->'autoplan'->>'origin_lat'    AS origin_lat,
       t.meta->'autoplan'->>'origin_lon'    AS origin_lon,
       t.meta->'autoplan'->>'dest_lat'      AS dest_lat,
       t.meta->'autoplan'->>'dest_lon'      AS dest_lon,
       t.updated_at
FROM public.trips t
WHERE t.status='confirmed'
  AND COALESCE(NULLIF(t.meta->'autoplan'->>'road_km',''),'') = '';

-- регионы, которых нет в region_centroids (по коду/названию)
CREATE OR REPLACE VIEW ops.missing_regions_v AS
WITH needed AS (
  SELECT DISTINCT UPPER(TRIM(t.meta->'autoplan'->>'origin_region')) AS region_key
  FROM public.trips t
  WHERE t.status='confirmed'
    AND COALESCE(NULLIF(t.meta->'autoplan'->>'road_km',''),'') = ''
    AND NULLIF(TRIM(t.meta->'autoplan'->>'origin_region'),'') IS NOT NULL
  UNION
  SELECT DISTINCT UPPER(TRIM(t.meta->'autoplan'->>'dest_region')) AS region_key
  FROM public.trips t
  WHERE t.status='confirmed'
    AND COALESCE(NULLIF(t.meta->'autoplan'->>'road_km',''),'') = ''
    AND NULLIF(TRIM(t.meta->'autoplan'->>'dest_region'),'') IS NOT NULL
)
SELECT n.region_key,
       (SELECT COUNT(*)
          FROM public.trips t
         WHERE UPPER(TRIM(t.meta->'autoplan'->>'origin_region'))=n.region_key
            OR UPPER(TRIM(t.meta->'autoplan'->>'dest_region'))=n.region_key
       ) AS trips_cnt
FROM needed n
WHERE NOT EXISTS (
  SELECT 1
    FROM public.region_centroids rc
   WHERE UPPER(rc.code)                = n.region_key
      OR public.fn_norm_key(rc.region) = public.fn_norm_key(n.region_key)
      OR public.fn_norm_key(rc.name)   = public.fn_norm_key(n.region_key)
)
ORDER BY trips_cnt DESC, n.region_key;

-- усреднённые центры по city_map (без зависимости от cm.city)
CREATE OR REPLACE VIEW ops.citymap_region_centers_v AS
SELECT UPPER(TRIM(region)) AS region_key,
       AVG(lat)::float     AS lat_avg,
       AVG(lon)::float     AS lon_avg,
       COUNT(*)            AS points
FROM public.city_map
WHERE lat IS NOT NULL AND lon IS NOT NULL
GROUP BY UPPER(TRIM(region));

-- медианные центры по фактическим координатам из trips
CREATE OR REPLACE VIEW ops.trips_region_centers_v AS
WITH src AS (
  SELECT UPPER(TRIM(meta->'autoplan'->>'origin_region')) AS region_key,
         NULLIF((meta->'autoplan'->>'origin_lat')::numeric,0) AS lat,
         NULLIF((meta->'autoplan'->>'origin_lon')::numeric,0) AS lon
  FROM public.trips
  UNION ALL
  SELECT UPPER(TRIM(meta->'autoplan'->>'dest_region')),
         NULLIF((meta->'autoplan'->>'dest_lat')::numeric,0),
         NULLIF((meta->'autoplan'->>'dest_lon')::numeric,0)
  FROM public.trips
)
SELECT region_key,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat) AS lat_med,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon) AS lon_med,
       COUNT(*) FILTER (WHERE lat IS NOT NULL AND lon IS NOT NULL) AS samples
FROM src
WHERE region_key IS NOT NULL
  AND lat IS NOT NULL AND lon IS NOT NULL
GROUP BY region_key;

-- подсказки, откуда взять координаты в region_centroids
CREATE OR REPLACE VIEW ops.region_centroids_suggest_v AS
SELECT m.region_key,
       cm.lat_avg AS lat_citymap,
       cm.lon_avg AS lon_citymap,
       cm.points  AS citymap_points,
       tr.lat_med AS lat_trips,
       tr.lon_med AS lon_trips,
       tr.samples AS trip_samples,
       COALESCE(cm.lat_avg, tr.lat_med) AS lat_suggest,
       COALESCE(cm.lon_avg, tr.lon_med) AS lon_suggest
FROM ops.missing_regions_v m
LEFT JOIN ops.citymap_region_centers_v cm ON cm.region_key = m.region_key
LEFT JOIN ops.trips_region_centers_v   tr ON tr.region_key = m.region_key;


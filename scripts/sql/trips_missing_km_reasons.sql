-- file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\scripts\sql\trips_missing_km_reasons.sql
-- FoxProFlow — причины отсутствия road_km у confirmed-трипов
-- ----------------------------------------------------------
-- Классификатор по 3 категориям:
--   • missing_regions   — нет origin_region и/или dest_region
--   • no_coords_in_meta — нет координат from_/to_ (lat/lon) в meta.autoplan.*
--   • other             — прочее (единичные кейсы, требующие адресной проверки)

WITH c AS (
  SELECT id,
         NULLIF(trim(meta->'autoplan'->>'origin_region'),'') AS o,
         NULLIF(trim(meta->'autoplan'->>'dest_region'),  '') AS d,
         NULLIF(trim(meta->'autoplan'->>'from_lat'),    '') AS flt,
         NULLIF(trim(meta->'autoplan'->>'from_lon'),    '') AS fln,
         NULLIF(trim(meta->'autoplan'->>'to_lat'),      '') AS tlt,
         NULLIF(trim(meta->'autoplan'->>'to_lon'),      '') AS tln
  FROM public.trips
  WHERE status='confirmed'
    AND COALESCE(NULLIF(meta->'autoplan'->>'road_km',''),'') = ''
)
SELECT CASE
         WHEN o IS NULL OR d IS NULL THEN 'missing_regions'
         WHEN (flt IS NULL OR fln IS NULL OR tlt IS NULL OR tln IS NULL) THEN 'no_coords_in_meta'
         ELSE 'other'
       END AS reason,
       count(*)
FROM c
GROUP BY 1
ORDER BY 2 DESC;

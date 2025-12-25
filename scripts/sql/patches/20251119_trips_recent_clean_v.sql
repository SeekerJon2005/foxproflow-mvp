-- 20251119_trips_recent_clean_v.sql
-- FoxProFlow / GEO+Routing
-- Чистая витрина последних рейсов без RU-UNK и Н/Д в регионах.

CREATE OR REPLACE VIEW public.trips_recent_clean_v AS
SELECT
  id,
  status,
  created_at,
  origin_region,
  dest_region,
  price_rub,
  road_km,
  drive_sec
FROM public.trips_recent_v
WHERE origin_region NOT IN ('RU-UNK', 'Н/Д')
  AND dest_region   NOT IN ('RU-UNK', 'Н/Д');

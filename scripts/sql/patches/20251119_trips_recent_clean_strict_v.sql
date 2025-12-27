-- file: scripts/sql/patches/20251119_trips_recent_clean_strict_v.sql
--
-- Витрина только для «чистых» рейсов:
--   • только рейсы с маршрутом (road_km / drive_sec не NULL);
--   • только за последние 3 дня.
--
-- Используется в UI/отчётности, чтобы не светить архивный мусор
-- и фокусироваться на свежих, полностью обогащённых рейсах.

CREATE OR REPLACE VIEW public.trips_recent_clean_strict_v AS
SELECT
  id,
  status,
  created_at,
  origin_region,
  dest_region,
  price_rub,
  road_km,
  drive_sec
FROM public.trips_recent_clean_v
WHERE created_at >= now() - interval '3 days'
  AND road_km IS NOT NULL
  AND drive_sec IS NOT NULL;

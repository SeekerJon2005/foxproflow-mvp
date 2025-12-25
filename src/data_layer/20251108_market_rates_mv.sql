-- market_rates_mv — базовая версия (опирается на public.freights, алиасы price/distance_km)
BEGIN;
DROP MATERIALIZED VIEW IF EXISTS public.market_rates_mv;

CREATE MATERIALIZED VIEW public.market_rates_mv AS
WITH base AS (
  SELECT
    COALESCE(loading_region, loading_region_code)  AS loading_region,
    COALESCE(unloading_region, unloading_region_code) AS unloading_region,
    (
      CASE
        WHEN loading_date IS NOT NULL THEN date_trunc('day', loading_date::timestamp)
        WHEN load_window_start IS NOT NULL THEN date_trunc('day', load_window_start)
        ELSE now()
      END
    )::date AS day,
    COALESCE(revenue_rub, price::numeric)          AS revenue_rub,
    COALESCE(distance, distance_km::numeric)       AS distance_km
  FROM public.freights
  WHERE COALESCE(loading_region, loading_region_code) IS NOT NULL
    AND COALESCE(unloading_region, unloading_region_code) IS NOT NULL
)
SELECT
  loading_region,
  unloading_region,
  day,
  SUM(revenue_rub)                                         AS revenue_sum,
  SUM(distance_km)                                         AS km_sum,
  (SUM(revenue_rub) / NULLIF(SUM(distance_km),0))::numeric AS rpm_avg,
  percentile_cont(0.5) WITHIN GROUP (
    ORDER BY CASE WHEN distance_km > 0 THEN revenue_rub / distance_km END
  )::numeric                                               AS rpm_p50
FROM base
GROUP BY 1,2,3;

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_rates_key
  ON public.market_rates_mv (loading_region, unloading_region, day);
COMMIT;

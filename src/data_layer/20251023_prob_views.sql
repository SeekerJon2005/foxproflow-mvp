-- 2025-10-23 — Probabilistic Views (OD-arrival, OD-price-quantiles) — FIXED

BEGIN;

-- A) Время в пути (часов) по дням
DROP MATERIALIZED VIEW IF EXISTS public.od_arrival_stats_mv;

CREATE MATERIALIZED VIEW public.od_arrival_stats_mv AS
WITH base AS (
  SELECT
    loading_region,
    unloading_region,
    DATE_TRUNC('day', loading_date)::date AS day,
    EXTRACT(EPOCH FROM (unloading_date - loading_date))/3600.0 AS hours_transit
  FROM public.freights_enriched_mv              -- ← FIX: правильное имя витрины
  WHERE loading_region IS NOT NULL
    AND unloading_region IS NOT NULL
    AND loading_date  IS NOT NULL
    AND unloading_date IS NOT NULL
    AND unloading_date >= loading_date
),
clean AS (
  SELECT *
  FROM base
  WHERE hours_transit IS NOT NULL AND hours_transit BETWEEN 1 AND 240
)
SELECT
  loading_region, unloading_region, day,
  COUNT(*)::int AS n,
  AVG(hours_transit) AS hours_avg,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY hours_transit) AS hours_p50
FROM clean
GROUP BY 1,2,3
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS ux_od_arrival_stats_mv
  ON public.od_arrival_stats_mv(loading_region, unloading_region, day);

-- B) Квантили rpm по OD × кузов × тоннаж
DROP MATERIALIZED VIEW IF EXISTS public.od_price_quantiles_mv;

CREATE MATERIALIZED VIEW public.od_price_quantiles_mv AS
WITH base AS (
  SELECT
    loading_region, unloading_region,
    COALESCE(NULLIF(body_type,''),'UNKNOWN') AS body_type,
    CASE
      WHEN weight IS NULL THEN 'UNKNOWN'
      WHEN (CASE WHEN weight > 1000 THEN weight/1000.0 ELSE weight END) >= 20 THEN '20t'
      WHEN (CASE WHEN weight > 1000 THEN weight/1000.0 ELSE weight END) >= 10 THEN '10t'
      WHEN (CASE WHEN weight > 1000 THEN weight/1000.0 ELSE weight END) >= 5  THEN '5t'
      ELSE '1.5t'
    END AS tonnage_class,
    rpm
  FROM public.freights_enriched_mv
  WHERE rpm IS NOT NULL AND rpm > 0
    AND loading_region IS NOT NULL
    AND unloading_region IS NOT NULL
)
SELECT
  loading_region, unloading_region, body_type, tonnage_class,
  COUNT(*)::int AS n,
  PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY rpm) AS rpm_p10,
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY rpm) AS rpm_p25,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY rpm) AS rpm_p50,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY rpm) AS rpm_p75,
  PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY rpm) AS rpm_p90
FROM base
GROUP BY 1,2,3,4
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS ux_od_price_quantiles_mv
  ON public.od_price_quantiles_mv(loading_region, unloading_region, body_type, tonnage_class);

COMMIT;

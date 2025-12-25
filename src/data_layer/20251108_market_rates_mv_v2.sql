BEGIN;

DROP MATERIALIZED VIEW IF EXISTS public.market_rates_mv;

CREATE MATERIALIZED VIEW public.market_rates_mv AS
SELECT
  f.loading_region,
  f.unloading_region,
  date_trunc('day', COALESCE(f.loading_date::timestamp, now()))::date AS day,
  SUM(f.revenue_rub)::numeric                                  AS revenue_sum,
  SUM(NULLIF(f.distance, 0))::numeric                          AS km_sum,
  (SUM(f.revenue_rub) / NULLIF(SUM(f.distance), 0))::numeric    AS rpm_avg
FROM public.freights f
WHERE f.loading_region  IS NOT NULL
  AND f.unloading_region IS NOT NULL
  AND f.revenue_rub     IS NOT NULL
  AND f.distance        IS NOT NULL
GROUP BY 1,2,3;

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_rates_key
  ON public.market_rates_mv (loading_region, unloading_region, day);

COMMIT;

-- file: src/data_layer/20251021_market_rates_mv.sql
BEGIN;

-- вспомогательная функция используется в cleanup-патчах
CREATE OR REPLACE FUNCTION public.ff_nullish(t text)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
           WHEN t IS NULL THEN TRUE
           WHEN btrim(upper(t)) IN ('Н/Д','N/A','NA','N\\A','-','—','NONE','NULL','N.D.') THEN TRUE
           WHEN btrim(t) = '' THEN TRUE
           ELSE FALSE
         END
$$;

DROP MATERIALIZED VIEW IF EXISTS public.market_rates_mv;

CREATE MATERIALIZED VIEW public.market_rates_mv AS
SELECT
  date_trunc('day', (loading_date AT TIME ZONE 'UTC'))::date AS day,
  loading_region, unloading_region,
  AVG(rpm)::float8                                  AS rpm_avg,
  percentile_disc(0.50) WITHIN GROUP (ORDER BY rpm) AS rpm_p50,
  COUNT(*)::int                                     AS n
FROM public.freights_enriched_mv
WHERE loading_date IS NOT NULL
  AND rpm IS NOT NULL
  AND NOT public.ff_nullish(loading_region)
  AND NOT public.ff_nullish(unloading_region)
GROUP BY 1,2,3
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_rates_mv
  ON public.market_rates_mv(day, loading_region, unloading_region);

COMMIT;

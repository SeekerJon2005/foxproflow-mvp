-- 2025-11-02 — Market rates + guard indexes (safe/idempotent)

BEGIN;

-- A) Дневные ставки рынка по OD
DROP MATERIALIZED VIEW IF EXISTS public.market_rates_mv;

CREATE MATERIALIZED VIEW public.market_rates_mv AS
WITH base AS (
  SELECT
    DATE_TRUNC('day', loading_date)::date AS day,
    loading_region,
    unloading_region,
    rpm
  FROM public.freights_enriched_mv
  WHERE rpm IS NOT NULL AND rpm > 0
    AND loading_date IS NOT NULL
    AND loading_region IS NOT NULL
    AND unloading_region IS NOT NULL
)
SELECT
  day, loading_region, unloading_region,
  COUNT(*)::int AS n,
  AVG(rpm)      AS rpm_avg,
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY rpm) AS rpm_p25,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY rpm) AS rpm_p50,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY rpm) AS rpm_p75
FROM base
GROUP BY 1,2,3
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_rates_mv
  ON public.market_rates_mv(day, loading_region, unloading_region);

-- B) Страхуем индексы на OD-витринах только если они уже существуют
DO $$
BEGIN
  IF to_regclass('public.od_arrival_stats_mv') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ux_od_arrival_stats_mv') THEN
      EXECUTE 'CREATE UNIQUE INDEX ux_od_arrival_stats_mv ON public.od_arrival_stats_mv(loading_region, unloading_region, day)';
    END IF;
  END IF;

  IF to_regclass('public.od_price_quantiles_mv') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ux_od_price_quantiles_mv') THEN
      EXECUTE 'CREATE UNIQUE INDEX ux_od_price_quantiles_mv ON public.od_price_quantiles_mv(loading_region, unloading_region, body_type, tonnage_class)';
    END IF;
  END IF;
END$$;

COMMIT;

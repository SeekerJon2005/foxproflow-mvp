-- od_price_quantiles_mv.sql — RPM-квантили по OD × кузов × тоннаж
-- Идемпотентное создание МV + индексы для CONCURRENTLY
-- Источник: public.freights_enriched_mv; RPM = revenue_rub / distance_km

DO $$
BEGIN
  IF to_regclass('public.od_price_quantiles_mv') IS NULL THEN
    EXECUTE $DDL$
      CREATE MATERIALIZED VIEW public.od_price_quantiles_mv AS
      WITH base AS (
        SELECT
          loading_region,
          unloading_region,
          body_type,
          CASE
            WHEN weight IS NULL THEN 'unknown'
            WHEN (CASE WHEN weight > 1000 THEN weight/1000.0 ELSE weight END) >= 20 THEN '20t'
            WHEN (CASE WHEN weight > 1000 THEN weight/1000.0 ELSE weight END) >= 10 THEN '10t'
            WHEN (CASE WHEN weight > 1000 THEN weight/1000.0 ELSE weight END) >= 5  THEN '5t'
            ELSE '1.5t'
          END AS tonnage_class,
          revenue_rub::numeric AS revenue_rub,
          distance::numeric    AS distance_km
        FROM public.freights_enriched_mv
        WHERE revenue_rub IS NOT NULL AND distance IS NOT NULL AND distance > 0
      )
      SELECT
        loading_region,
        unloading_region,
        body_type,
        tonnage_class,
        /* При желании добавьте p25/p10 — автоплан возьмёт нужный квантиль из ENV */
        percentile_cont(0.50) WITHIN GROUP (ORDER BY revenue_rub/NULLIF(distance_km,0)) AS rpm_p50,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY revenue_rub/NULLIF(distance_km,0)) AS rpm_p75,
        percentile_cont(0.90) WITHIN GROUP (ORDER BY revenue_rub/NULLIF(distance_km,0)) AS rpm_p90,
        COUNT(*) AS n
      FROM base
      GROUP BY 1,2,3,4
      WITH NO DATA
    $DDL$;
  END IF;
END$$;

-- Индексы (уникальный — для REFRESH CONCURRENTLY; btree — для типичных фильтров)
CREATE UNIQUE INDEX IF NOT EXISTS ux_od_price_quantiles_unique
  ON public.od_price_quantiles_mv (loading_region, unloading_region, body_type, tonnage_class);

CREATE INDEX IF NOT EXISTS ix_od_price_key
  ON public.od_price_quantiles_mv (loading_region, unloading_region, body_type, tonnage_class);

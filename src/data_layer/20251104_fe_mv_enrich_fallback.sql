-- 2025-11-04 — freights_enriched_mv (payload fallback + ff_num helpers)
BEGIN;

-- временно убираем зависящие витрины (пересоздадим и наполним ниже отдельными скриптами)
DROP MATERIALIZED VIEW IF EXISTS public.market_rates_mv;
DROP MATERIALIZED VIEW IF EXISTS public.od_price_quantiles_mv;
DROP MATERIALIZED VIEW IF EXISTS public.od_arrival_stats_mv;

DROP MATERIALIZED VIEW IF EXISTS public.freights_enriched_mv;

CREATE MATERIALIZED VIEW public.freights_enriched_mv AS
WITH f0 AS (SELECT f.*, to_jsonb(f.*) AS j FROM public.freights f)
SELECT
  NULLIF(j->>'source','')     AS source,
  NULLIF(j->>'source_uid','') AS source_uid,

  public.ff_region_by_text(
    COALESCE(
      public.ff_get(j,'loading_region'),
      public.ff_get(j,'origin_region'),
      public.ff_get(j,'origin'),
      public.ff_get(j,'payload.loading_region'),
      public.ff_get(j,'payload.origin_region'),
      public.ff_get(j,'payload.origin')
    )
  ) AS loading_region,

  public.ff_region_by_text(
    COALESCE(
      public.ff_get(j,'unloading_region'),
      public.ff_get(j,'destination_region'),
      public.ff_get(j,'destination'),
      public.ff_get(j,'payload.unloading_region'),
      public.ff_get(j,'payload.destination_region'),
      public.ff_get(j,'payload.destination')
    )
  ) AS unloading_region,

  COALESCE(
    public.ff_try_ts(public.ff_get(j,'loading_date')),
    public.ff_try_ts(public.ff_get(j,'payload.loading_date'))
  ) AS loading_date,

  COALESCE(
    public.ff_try_ts(public.ff_get(j,'unloading_date')),
    public.ff_try_ts(public.ff_get(j,'payload.unloading_date'))
  ) AS unloading_date,

  public.ff_num_from_keys(j, ARRAY[
    'distance','distance_km','payload.distance','payload.distance_km'
  ]) AS distance,

  public.ff_num_from_keys(j, ARRAY[
    'revenue_rub','price','payload.revenue_rub','payload.price'
  ]) AS revenue_rub,

  COALESCE(
    NULLIF(public.ff_get(j,'body_type'),''),
    NULLIF(public.ff_get(j,'payload.body_type'),''),
    'UNKNOWN'
  ) AS body_type,

  public.ff_num_from_keys(j, ARRAY[
    'weight','payload.weight'
  ]) AS weight,

  COALESCE(
    public.ff_num_from_keys(j, ARRAY['rpm','payload.rpm']),
    NULLIF(
      public.ff_num_from_keys(j, ARRAY['revenue_rub','price','payload.revenue_rub','payload.price'])
      /
      NULLIF(public.ff_num_from_keys(j, ARRAY['distance','distance_km','payload.distance','payload.distance_km']), 0)
    ,0)
  ) AS rpm,

  COALESCE(public.ff_try_ts(public.ff_get(j,'created_at')), NOW()) AS created_at,
  COALESCE(j->'payload', '{}'::jsonb) AS payload
FROM f0
WITH NO DATA;

CREATE INDEX IF NOT EXISTS ix_fe_loading_date ON public.freights_enriched_mv(loading_date);
CREATE INDEX IF NOT EXISTS ix_fe_regions      ON public.freights_enriched_mv(loading_region, unloading_region);
CREATE INDEX IF NOT EXISTS ix_fe_rpm          ON public.freights_enriched_mv(rpm);

COMMIT;

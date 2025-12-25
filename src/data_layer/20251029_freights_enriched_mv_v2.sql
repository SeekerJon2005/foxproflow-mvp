-- file: src/data_layer/20251029_freights_enriched_mv_v2.sql
DO $do$
DECLARE
  src regclass;
  src_table text;
BEGIN
  IF to_regclass('public.freights') IS NOT NULL THEN
    src := 'public.freights'::regclass;
  ELSIF to_regclass('public.loads') IS NOT NULL THEN
    src := 'public.loads'::regclass;
  ELSE
    RAISE EXCEPTION 'Neither public.freights nor public.loads exist';
  END IF;

  SELECT relname INTO src_table FROM pg_class WHERE oid = src;

  EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS public.freights_enriched_mv';

  EXECUTE format($SQL$
    CREATE MATERIALIZED VIEW public.freights_enriched_mv AS
    SELECT
      COALESCE(loading_region, load_region, origin_region)    AS loading_region,
      COALESCE(unloading_region, unload_region, dest_region)  AS unloading_region,
      COALESCE(body, body_type)::text                          AS body_type,
      COALESCE(weight, weight_kg, weight_tons*1000)::numeric   AS weight,
      COALESCE(distance, km, od_km)::numeric                   AS distance,
      COALESCE(price, price_rub, revenue_rub)::numeric         AS revenue_rub,
      COALESCE(loading_date, load_dt, pickup_dt)::timestamptz  AS loading_date,
      COALESCE(unloading_date, unload_dt, delivery_dt)::timestamptz AS unloading_date,
      CASE WHEN COALESCE(distance, km, od_km) > 0
           THEN COALESCE(price, price_rub, revenue_rub)::numeric / NULLIF(COALESCE(distance, km, od_km)::numeric, 0)
           ELSE NULL END AS rpm
    FROM %I
    WITH NO DATA;
  $SQL$, src_table);

  CREATE UNIQUE INDEX IF NOT EXISTS ux_freights_enriched_mv_rowid
    ON public.freights_enriched_mv(loading_region, unloading_region, loading_date, revenue_rub)
    WHERE loading_region IS NOT NULL AND unloading_region IS NOT NULL;
END
$do$;

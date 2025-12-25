-- file: src/data_layer/20251103_citynorm_patch_fix.sql
BEGIN;

CREATE OR REPLACE FUNCTION public.ff_city_norm(t text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  WITH s AS (SELECT upper(btrim(coalesce($1,''))) AS x)
  SELECT NULLIF(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          regexp_replace((SELECT x FROM s),'^(Г\.\s*|С\.\s*|ПГТ\s*|РП\s*|ГОРОД\s+)', '', 'gi'),
          '\s+Г\.?$', '', 'gi'),
        '\s+', ' ', 'g'),
      '^\s+|\s+$', '', 'g'
    ), ''
  );
$$;

CREATE OR REPLACE FUNCTION public.ff_region_by_city(city text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  WITH c AS (SELECT public.ff_city_norm($1) AS c)
  SELECT COALESCE(
    (SELECT region FROM public.city_to_region_map WHERE upper(btrim(city))=(SELECT c FROM c)),
    (SELECT c FROM c)
  );
$$;

DROP MATERIALIZED VIEW IF EXISTS public.market_rates_mv;
DROP MATERIALIZED VIEW IF EXISTS public.od_price_quantiles_mv;
DROP MATERIALIZED VIEW IF EXISTS public.od_arrival_stats_mv;
DROP MATERIALIZED VIEW IF EXISTS public.freights_enriched_mv;

-- (дальше — пересбор freights_enriched_mv и двух витрин; см. v2/v3 и cleanup-патч)
COMMIT;

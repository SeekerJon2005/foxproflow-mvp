BEGIN;
DROP MATERIALIZED VIEW IF EXISTS public.freights_enriched_mv;
CREATE MATERIALIZED VIEW public.freights_enriched_mv AS
SELECT
  f.id, f.source, f.source_uid,
  f.loading_region, f.unloading_region,
  f.loading_date, f.unloading_date,
  f.body_type, f.weight,
  f.revenue_rub, f.distance,
  (CASE WHEN f.distance>0 AND f.revenue_rub IS NOT NULL THEN f.revenue_rub/f.distance END)::numeric AS rpm
FROM public.freights f
WHERE f.source_uid LIKE 'smoke-freight-%';
CREATE UNIQUE INDEX IF NOT EXISTS ux_freights_enriched_key ON public.freights_enriched_mv (source, source_uid);
CREATE INDEX IF NOT EXISTS ix_freights_enriched_od       ON public.freights_enriched_mv (loading_region, unloading_region);
COMMIT;

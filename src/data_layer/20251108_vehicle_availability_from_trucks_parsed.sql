-- vehicle_availability_mv из trucks_parsed
BEGIN;
DROP MATERIALIZED VIEW IF EXISTS public.vehicle_availability_mv;

CREATE MATERIALIZED VIEW public.vehicle_availability_mv AS
SELECT
  tp.source_uid                                  AS truck_id,
  UPPER(TRIM(tp.region))                         AS available_region,
  COALESCE(tp.available_from, now())::timestamptz AS available_from
FROM public.trucks_parsed tp
WHERE NULLIF(TRIM(tp.source_uid), '') IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicle_availability_key
  ON public.vehicle_availability_mv(truck_id);

CREATE INDEX IF NOT EXISTS ix_vehicle_availability_region
  ON public.vehicle_availability_mv(available_region);

CREATE INDEX IF NOT EXISTS ix_vehicle_availability_from
  ON public.vehicle_availability_mv(available_from);
COMMIT;

BEGIN;

-- 1) Уточним, какие колонки в MV (для контроля глазами)
-- SELECT column_name, data_type
-- FROM information_schema.columns
-- WHERE table_schema='public' AND table_name='vehicle_availability_mv'
-- ORDER BY ordinal_position;

-- 2) Безопасно переопределяем VIEW на объединение (MV + trucks_parsed)
CREATE OR REPLACE VIEW public.vehicle_availability_v AS
SELECT
  mv.truck_id,
  mv.available_region,
  mv.available_from
FROM public.vehicle_availability_mv AS mv

UNION ALL
SELECT
  tp.source_uid                               AS truck_id,
  UPPER(TRIM(tp.region))                      AS available_region,
  COALESCE(tp.available_from, now())::timestamptz AS available_from
FROM public.trucks_parsed AS tp
WHERE NULLIF(TRIM(tp.source_uid),'') IS NOT NULL;

-- Иногда поверх есть синоним-обёртка vehicle_availability — выровняем и её
CREATE OR REPLACE VIEW public.vehicle_availability AS
SELECT * FROM public.vehicle_availability_v;

COMMIT;

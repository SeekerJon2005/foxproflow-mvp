-- 2025-11-19 — FoxProFlow
-- Патч: плановая цена рейса (price_rub_plan) в public.trips
-- NDC: только ADD COLUMN + мягкий UPDATE по meta.autoplan.price

DO $$
BEGIN
  -- 1. Создаём колонку, если её ещё нет
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name   = 'trips'
      AND column_name  = 'price_rub_plan'
  ) THEN
    ALTER TABLE public.trips
      ADD COLUMN price_rub_plan numeric(14,2);

    COMMENT ON COLUMN public.trips.price_rub_plan IS
      'Плановая цена рейса в рублях (из meta.autoplan.price или ценовой витрины)';
  END IF;
END$$;

-- 2. Первичный бэктилл: подтягиваем цену из meta.autoplan.price
--    Пустые строки трактуем как "нет данных".
--    0 считаем валидной ценой (особый кейс, но цена есть).
UPDATE public.trips t
SET price_rub_plan =
      COALESCE(
        NULLIF(t.meta->'autoplan'->>'price', '')::numeric,
        t.price_rub_plan
      )
WHERE t.price_rub_plan IS NULL
  AND t.meta ? 'autoplan';

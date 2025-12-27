-- file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\scripts\sql\availability_sample.sql
-- FoxProFlow — выборка доступности ТС (vehicle_availability_mv)
-- --------------------------------------------------------------
-- Показывает ближайшую доступность ТС (truck_id, available_from, available_region)
-- из витрины public.vehicle_availability_mv.
--
-- Использование в psql (рекомендуется задать переменные перед запуском):
--   \set region ''            -- код региона (напр. 'RU-MOW'); пустая строка = без фильтра
--   \set limit  50            -- сколько строк вернуть
--   \i scripts/sql/availability_sample.sql
--
-- Примечания:
--   • Если у вас ещё нет витрины vehicle_availability_mv, используйте как источник
--     фид public.autoplan_availability_feed (замените имя таблицы ниже).
--   • Поля, ожидаемые воркером: truck_id (uuid), available_from (timestamptz), available_region (text).

SELECT
  truck_id,
  available_from,
  available_region
FROM public.vehicle_availability_mv
WHERE (:'region' = '' OR UPPER(COALESCE(available_region,'')) = UPPER(:'region'))
ORDER BY available_from ASC
LIMIT :limit;

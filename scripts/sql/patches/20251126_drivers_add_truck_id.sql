-- 20251126_drivers_add_truck_id.sql
-- FoxProFlow — логистика / приложение водителя
-- Цель: добавить привязку водителя к ТС (truck_id) для выдачи рейсов
-- через /driver/trips/assigned и связанные вью/сервисы.
--
-- Требования:
--  - Только недеструктивные изменения (NDC).
--  - Повторный запуск миграции безопасен (IF NOT EXISTS).
--  - Никаких внешних ключей, чтобы не ломать существующие данные;
--    связь driver.truck_id -> trips.truck_id / vehicles.* реализуется на уровне сервисов.

BEGIN;

-- 1. Добавляем колонку truck_id в public.drivers, если её ещё нет.
--    Колонка допускает NULL: не все водители обязаны быть привязаны к ТС.
ALTER TABLE public.drivers
    ADD COLUMN IF NOT EXISTS truck_id uuid;

-- 2. Индекс по truck_id для быстрых JOIN/фильтров:
--    - поиск водителей по ТС;
--    - выборка рейсов по списку водителей через join.
CREATE INDEX IF NOT EXISTS drivers_truck_id_idx
    ON public.drivers(truck_id);

COMMIT;

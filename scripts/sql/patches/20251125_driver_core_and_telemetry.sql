-- 20251125_driver_core_and_telemetry.sql
-- FoxProFlow — ядро водителей + телеметрия Driver App.
-- NDC: только CREATE TABLE IF NOT EXISTS, ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
--      CREATE INDEX IF NOT EXISTS. Никаких DROP/ALTER COLUMN.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Справочник водителей
CREATE TABLE IF NOT EXISTS public.drivers (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name          text,
    phone              text UNIQUE,
    license_number     text,
    license_categories text[],
    adr_classes        text[],
    is_active          boolean     NOT NULL DEFAULT TRUE,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.drivers IS
    'Водители ТС (Driver App / CRM / диспетчерский модуль).';

COMMENT ON COLUMN public.drivers.full_name IS 'ФИО водителя.';
COMMENT ON COLUMN public.drivers.phone IS 'Телефон (используется для авторизации Driver App).';
COMMENT ON COLUMN public.drivers.license_number IS 'Номер водительского удостоверения.';
COMMENT ON COLUMN public.drivers.license_categories IS 'Категории ВУ (B, C, E и т.п.).';
COMMENT ON COLUMN public.drivers.adr_classes IS 'Классы ADR (опасные грузы).';
COMMENT ON COLUMN public.drivers.is_active IS 'Признак, что водитель активен и может получать рейсы.';

-- 2. Связь ТС ↔ водитель
ALTER TABLE public.trucks
    ADD COLUMN IF NOT EXISTS driver_id uuid;

CREATE INDEX IF NOT EXISTS idx_trucks_driver_id
    ON public.trucks (driver_id);

COMMENT ON COLUMN public.trucks.driver_id IS
    'Текущий закреплённый за ТС водитель (если есть).';

-- 3. Доп. поля в trips под Driver App
ALTER TABLE public.trips
    ADD COLUMN IF NOT EXISTS driver_ack_at timestamptz,
    ADD COLUMN IF NOT EXISTS completed_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_trips_driver_ack_at
    ON public.trips (driver_ack_at);

CREATE INDEX IF NOT EXISTS idx_trips_completed_at
    ON public.trips (completed_at);

COMMENT ON COLUMN public.trips.driver_ack_at IS
    'Когда водитель впервые увидел/подтвердил рейс в Driver App.';
COMMENT ON COLUMN public.trips.completed_at IS
    'Когда рейс был завершён (по нажатию «завершить» или по факту выгрузки).';

-- 4. Таблица телеметрии от водителя
CREATE TABLE IF NOT EXISTS public.driver_telemetry (
    id           bigserial PRIMARY KEY,
    trip_id      uuid              NOT NULL,
    driver_id    uuid,
    truck_id     uuid,
    ts           timestamptz       NOT NULL,
    lat          double precision  NOT NULL,
    lon          double precision  NOT NULL,
    speed_kph    numeric(6,2),
    heading_deg  numeric(6,2),
    accuracy_m   numeric(6,2),
    source       text              NOT NULL DEFAULT 'driver_app',
    payload      jsonb             NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_driver_telemetry_trip_ts
    ON public.driver_telemetry (trip_id, ts);

CREATE INDEX IF NOT EXISTS idx_driver_telemetry_driver_ts
    ON public.driver_telemetry (driver_id, ts);

COMMENT ON TABLE public.driver_telemetry IS
    'Сырые GPS-точки, присланные Driver App, для построения фактических треков и off-route анализа.';

COMMENT ON COLUMN public.driver_telemetry.trip_id IS
    'Рейс, к которому относится точка.';
COMMENT ON COLUMN public.driver_telemetry.driver_id IS
    'Водитель, отправивший точку (если известен).';
COMMENT ON COLUMN public.driver_telemetry.truck_id IS
    'ТС, с которого пришла точка (если известно).';
COMMENT ON COLUMN public.driver_telemetry.ts IS
    'Время фиксации точки в UTC.';
COMMENT ON COLUMN public.driver_telemetry.lat IS
    'Широта в градусах.';
COMMENT ON COLUMN public.driver_telemetry.lon IS
    'Долгота в градусах.';
COMMENT ON COLUMN public.driver_telemetry.speed_kph IS
    'Скорость в км/ч (как передал телефон).';
COMMENT ON COLUMN public.driver_telemetry.heading_deg IS
    'Азимут движения в градусах (0–360), если доступен.';
COMMENT ON COLUMN public.driver_telemetry.accuracy_m IS
    'Оценка точности GPS в метрах.';
COMMENT ON COLUMN public.driver_telemetry.source IS
    'Источник точки (driver_app, тесты и т.п.).';
COMMENT ON COLUMN public.driver_telemetry.payload IS
    'Дополнительные поля телеметрии в сыром jsonb-формате.';

-- 5. Тестовый водитель для стенда (связываем с TEST-TRUCK-001, если он есть)
INSERT INTO public.drivers (id, full_name, phone, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'TEST DRIVER 001',
    '+70000000001',
    TRUE
)
ON CONFLICT (id) DO NOTHING;

UPDATE public.trucks
SET driver_id = '00000000-0000-0000-0000-000000000001'
WHERE driver_id IS NULL
  AND name = 'TEST-TRUCK-001';

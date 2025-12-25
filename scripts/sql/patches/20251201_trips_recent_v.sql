-- 20251201_trips_recent_v.sql
-- FoxProFlow — вьюха последних рейсов для routing smoke / health-check
-- NDC: меняем только VIEW и индекс, базовые таблицы не трогаем.

-- Индекс для ускорения выборок "последние рейсы"
-- (ORDER BY created_at DESC LIMIT N)
CREATE INDEX IF NOT EXISTS trips_recent_created_at_idx
    ON public.trips (created_at, id);

-- Аккуратно пересоздаём вьюху: если уже есть — дропаем и создаём заново
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM   pg_views
        WHERE  schemaname = 'public'
        AND    viewname   = 'trips_recent_v'
    ) THEN
        DROP VIEW public.trips_recent_v;
    END IF;
END$$;

CREATE VIEW public.trips_recent_v AS
SELECT
    t.id               AS id,              -- для старых скриптов (ff-routing-smoke)
    t.id               AS trip_id,         -- более говорящая колонка
    t.status           AS status,
    t.created_at       AS created_at,
    t.confirmed_at     AS confirmed_at,
    t.loading_region   AS loading_region,
    t.unloading_region AS unloading_region,
    t.loading_region   AS origin_region,   -- alias для совместимости
    t.unloading_region AS dest_region,     -- alias для совместимости
    NULL::numeric      AS road_km,         -- заглушка; позже можно заменить на сумму по trip_segments
    NULL::integer      AS drive_sec,       -- заглушка; позже можно заменить на сумму по trip_segments
    t.price_rub_plan   AS price_rub,       -- alias под ожидания routing-smoke
    t.price_rub_plan   AS trip_price_rub,  -- более точное имя
    t.meta             AS meta
FROM public.trips t
ORDER BY t.created_at DESC
LIMIT 100;

COMMENT ON VIEW public.trips_recent_v IS
  'Последние рейсы (для диагностических скриптов: routing smoke, phase0 health-check и т.п.).';

COMMENT ON COLUMN public.trips_recent_v.id               IS 'ID рейса (public.trips.id), для совместимости со старыми скриптами.';
COMMENT ON COLUMN public.trips_recent_v.trip_id          IS 'ID рейса (public.trips.id).';
COMMENT ON COLUMN public.trips_recent_v.status           IS 'Статус рейса (planned/confirmed/cancelled и т.п.).';
COMMENT ON COLUMN public.trips_recent_v.created_at       IS 'Когда рейс был создан в системе.';
COMMENT ON COLUMN public.trips_recent_v.confirmed_at     IS 'Когда рейс был подтверждён (если применимо).';
COMMENT ON COLUMN public.trips_recent_v.loading_region   IS 'Регион погрузки (код региона).';
COMMENT ON COLUMN public.trips_recent_v.unloading_region IS 'Регион выгрузки (код региона).';
COMMENT ON COLUMN public.trips_recent_v.origin_region    IS 'Регион погрузки (alias loading_region, для совместимости).';
COMMENT ON COLUMN public.trips_recent_v.dest_region      IS 'Регион выгрузки (alias unloading_region, для совместимости).';
COMMENT ON COLUMN public.trips_recent_v.road_km          IS 'Дистанция по маршруту (км); пока заглушка NULL, можно заменить на сумму по trip_segments.';
COMMENT ON COLUMN public.trips_recent_v.drive_sec        IS 'Время в пути (сек); пока заглушка NULL, можно заменить на сумму по trip_segments.';
COMMENT ON COLUMN public.trips_recent_v.price_rub        IS 'Плановая цена рейса в рублях (price_rub_plan), alias для совместимости.';
COMMENT ON COLUMN public.trips_recent_v.trip_price_rub   IS 'Плановая цена рейса в рублях (price_rub_plan).';
COMMENT ON COLUMN public.trips_recent_v.meta             IS 'Связанные метаданные (JSONB) из trips.meta.';

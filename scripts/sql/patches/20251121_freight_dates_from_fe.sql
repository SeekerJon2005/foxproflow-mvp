-- scripts/sql/patches/20251121_freight_dates_from_fe.sql
--
-- Назначение:
--   Построить/пересобрать таблицу public.freight_dates с датами
--   погрузки/выгрузки на основе витрины public.freights_enriched_mv.
--
-- Формула:
--   unloading_date = loading_date
--                    + LOAD_DURATION_H
--                    + distance / AUTOPLAN_AVG_SPEED_KMH
--                    + UNLOAD_DURATION_H
--
-- Использование:
--   DO-скрипт идемпотентен на уровне схемы: при каждом запуске
--   полностью пересоздаёт public.freight_dates из актуального
--   состояния public.freights_enriched_mv.
--
-- Важно:
--   - Таблица public.freight_dates является производной витриной,
--     а не источником данных: её пересборка не считается
--     "деструктивной" для бизнес-логики.
--   - Первичный ключ (source, source_uid) синхронизирован с freights.

DO $$
DECLARE
    v_speed_kmh       numeric := 55;  -- AUTOPLAN_AVG_SPEED_KMH (из .env)
    v_load_h          numeric := 2;   -- LOAD_DURATION_H
    v_unload_h        numeric := 2;   -- UNLOAD_DURATION_H
BEGIN
    RAISE NOTICE 'Building/refreshing public.freight_dates: speed=%, load_h=%, unload_h=%',
        v_speed_kmh, v_load_h, v_unload_h;

    -- 0. На всякий случай дропаем старую версию таблицы, если была.
    DROP TABLE IF EXISTS public.freight_dates;

    -- 1. Таблица с датами (создаём заново, чистая витрина)
    CREATE TABLE public.freight_dates (
        source         text        NOT NULL,
        source_uid     text        NOT NULL,
        loading_date   timestamptz NOT NULL,
        unloading_date timestamptz NOT NULL,
        PRIMARY KEY (source, source_uid)
    );

    -- 2. Заполняем расчётными датами на основе текущего состояния FE.
    INSERT INTO public.freight_dates (source, source_uid, loading_date, unloading_date)
    SELECT
        fe.source,
        fe.source_uid,
        fe.loading_date,
        fe.loading_date
          + (v_load_h || ' hours')::interval
          + ((fe.distance / NULLIF(v_speed_kmh, 0)) || ' hours')::interval
          + (v_unload_h || ' hours')::interval
    FROM public.freights_enriched_mv AS fe
    WHERE fe.loading_date IS NOT NULL
      AND fe.distance    IS NOT NULL
      AND fe.source      IS NOT NULL      -- отбрасываем записи без идентификатора
      AND fe.source_uid  IS NOT NULL;     -- чтобы не ловить NOT NULL violation

    RAISE NOTICE 'freight_dates populated: % rows',
        (SELECT count(*) FROM public.freight_dates);
END $$;

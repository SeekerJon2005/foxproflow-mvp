-- 20251123_freights_core.sql
-- Базовое ядро хранения грузов и ATI-сырых данных
-- Таблицы:
--   * public.freights            — нормализованные грузы (по всем источникам, в т.ч. ATI)
--   * public.freights_ati_raw    — сырые JSON/HTML-документы ATI
--   * public.freights_enriched_mv — простая витрина по freights
--   * public.freight_dates       — расчётные даты погрузки/выгрузки для автоплана

-- 0. На всякий случай — схема analytics (нужна для аналитики по ставкам ATI)
CREATE SCHEMA IF NOT EXISTS analytics;

-- 1. Основная таблица нормализованных грузов
CREATE TABLE IF NOT EXISTS public.freights (
    id               bigserial PRIMARY KEY,
    created_at       timestamptz NOT NULL DEFAULT now(),

    -- Базовые даты
    loading_date     date,
    unloading_date   date,

    -- Региональная агрегация (для коридоров ATI и динамического RPM)
    loading_region   text,
    unloading_region text,

    -- Технические поля парсинга/источника
    parsed_at        timestamptz,
    payload          jsonb,

    source           text NOT NULL,  -- 'ati', 'ati_html', 'manual', '…'
    source_uid       text NOT NULL,  -- внешний ID внутри источника

    -- Задел под аналитику ATI
    loading_city     text,
    unloading_city   text,
    distance_km      numeric,
    price_rub        numeric,
    weight_tons      numeric
);

-- Уникальность пары (source, source_uid) — защищаемся от дублей
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'freights_source_uid_uq'
          AND conrelid = 'public.freights'::regclass
    ) THEN
        ALTER TABLE public.freights
            ADD CONSTRAINT freights_source_uid_uq
            UNIQUE (source, source_uid);
    END IF;
END
$$;

-- 2. Мат. витрина по грузам (упрощённая "enriched" витрина)
DROP MATERIALIZED VIEW IF EXISTS public.freights_enriched_mv;

CREATE MATERIALIZED VIEW public.freights_enriched_mv AS
SELECT
    f.id,
    f.source,
    f.source_uid,
    f.loading_date,
    f.unloading_date,
    f.loading_region,
    f.unloading_region,
    f.loading_city,
    f.unloading_city,
    f.distance_km AS distance,
    f.price_rub,
    f.weight_tons,
    f.created_at
FROM public.freights AS f;

CREATE UNIQUE INDEX IF NOT EXISTS freights_enriched_mv_source_uid_uq
    ON public.freights_enriched_mv (source, source_uid);

-- 3. Таблица freight_dates — расчётные окна по каждой заявке
CREATE TABLE IF NOT EXISTS public.freight_dates (
    id             bigserial PRIMARY KEY,
    source         text NOT NULL,
    source_uid     text NOT NULL,
    loading_date   date NOT NULL,
    unloading_date date NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Уникальность на уровне (source, source_uid) для UPSERT’ов
CREATE UNIQUE INDEX IF NOT EXISTS freight_dates_source_uid_uq
    ON public.freight_dates (source, source_uid);

-- 4. Сырые ATI-документы: public.freights_ati_raw
CREATE TABLE IF NOT EXISTS public.freights_ati_raw (
    id          bigserial PRIMARY KEY,
    src         text        NOT NULL,               -- 'ati_html_region' / 'ati_html' / 'ati'
    external_id text,                               -- ID груза/объявления на ATI
    loaded_at   timestamptz NOT NULL DEFAULT now(), -- когда подтянули этот JSON
    payload     jsonb       NOT NULL                -- сырое содержимое (распарсенный JSON/HTML)
);

-- Индекс по (src, loaded_at DESC) для выборок по "свежести"
CREATE INDEX IF NOT EXISTS freights_ati_raw_src_loaded_at_idx
    ON public.freights_ati_raw (src, loaded_at DESC);

-- Колонка parsed_at — когда запись была реально разобрана в public.freights
ALTER TABLE public.freights_ati_raw
    ADD COLUMN IF NOT EXISTS parsed_at timestamptz;

-- Для уже существующих строк (если появятся при миграции) — проставляем parsed_at из loaded_at,
-- чтобы фильтр по датам в etl.freights.from_ati не выбрасывал их.
UPDATE public.freights_ati_raw
SET parsed_at = loaded_at
WHERE parsed_at IS NULL;

-- Уникальность (src, external_id) под ON CONFLICT в парсере
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'freights_ati_raw_src_external_id_uq'
          AND conrelid = 'public.freights_ati_raw'::regclass
    ) THEN
        ALTER TABLE public.freights_ati_raw
            ADD CONSTRAINT freights_ati_raw_src_external_id_uq
            UNIQUE (src, external_id);
    END IF;
END
$$;

BEGIN;

-- 1. Базовая таблица public.city_map
CREATE TABLE IF NOT EXISTS public.city_map (
    id          bigserial PRIMARY KEY,
    region_raw  text NOT NULL,                -- сырой текст региона/города ("ЕКАТЕРИНБУРГ НД" и т.п.)
    norm_key    text NOT NULL,                -- нормализованный ключ (fn_norm_key(region_raw))
    city_name   text,                         -- человекочитаемое имя города
    region_code text,                         -- код региона (RU-SVE и т.п.)
    lat         double precision,             -- широта
    lon         double precision,             -- долгота
    meta        jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS city_map_norm_key_uq
    ON public.city_map(norm_key);

-- 2. Очередь автозаполнения ops.citymap_autofill_queue
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.citymap_autofill_queue (
    id              bigserial PRIMARY KEY,
    region_raw      text NOT NULL,
    norm_key        text,
    side            text NOT NULL,           -- 'src' или 'dst'
    segs_count      bigint,                  -- сколько сегментов с такой дыркой
    d               date NOT NULL,           -- день, за который зафиксирована дыра
    status          text NOT NULL DEFAULT 'pending',
    citymap_id      bigint,                  -- ссылка на public.city_map.id (пока без FK)
    provider        text,
    attempts        integer NOT NULL DEFAULT 0,
    last_attempt_at timestamptz,
    last_status     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS citymap_autofill_queue_region_side_d_uq
    ON ops.citymap_autofill_queue(region_raw, side, d);

-- 3. Заглушка представления analytics.city_map_gaps_long_v
-- Позже заменим на реальную аналитику по trip_segments, сейчас — пустой view с правильной сигнатурой.
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.city_map_gaps_long_v AS
SELECT
    NULL::text   AS region_raw,
    NULL::text   AS side,
    0::bigint    AS segs_count,
    CURRENT_DATE AS d
WHERE false;

COMMIT;

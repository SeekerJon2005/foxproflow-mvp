-- scripts/sql/patches/20251120_analytics_freights_ati_norm_v.sql
-- Нормализация ATI-фрахтов в аналитическую витрину
--
-- Источник: public.freights_ati_raw (src, external_id, parsed_at, payload).
-- Все остальные поля вытаскиваются из payload->'raw'.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.freights_ati_norm_v AS
WITH src AS (
    SELECT
        -- Источник и идентификатор из живой таблицы
        r.src                                             AS source,
        r.external_id                                     AS source_uid,

        -- Стабильный hash: id из raw, если есть, иначе external_id
        md5(
            COALESCE(
                r.payload->'raw'->>'id',
                r.external_id
            )
        )                                                 AS hash,

        -- Город погрузки
        COALESCE(
            NULLIF(trim(r.payload->'raw'->>'loading_city'), ''),
            NULLIF(trim(r.payload->'raw'->>'from_city'), ''),
            NULLIF(trim(r.payload->'raw'->>'from'), '')
        )                                                 AS loading_city,

        -- Город выгрузки
        COALESCE(
            NULLIF(trim(r.payload->'raw'->>'unloading_city'), ''),
            NULLIF(trim(r.payload->'raw'->>'to_city'), ''),
            NULLIF(trim(r.payload->'raw'->>'to'), '')
        )                                                 AS unloading_city,

        -- Описание груза / кузов
        NULLIF(trim(r.payload->'raw'->>'cargo'), '')       AS cargo,
        NULLIF(trim(r.payload->'raw'->>'body_type'), '')   AS body_type,

        -- Дата погрузки для аналитики:
        -- В сыром ATI поле loading_date некастабельно, поэтому берём дату парсинга.
        r.parsed_at::date                                 AS loading_date,

        -- Вес (тонны), из строки с возможными пробелами/единицами
        NULLIF(
            regexp_replace(
                COALESCE(r.payload->'raw'->>'weight', ''),
                '[^0-9\.]',
                '',
                'g'
            ),
            ''
        )::numeric                                        AS weight_t,

        -- Объём (м³)
        NULLIF(
            regexp_replace(
                COALESCE(r.payload->'raw'->>'volume', ''),
                '[^0-9\.]',
                '',
                'g'
            ),
            ''
        )::numeric                                        AS volume_m3,

        -- Цена (руб.): вытаскиваем, чистим от " руб." и пробелов
        NULLIF(
            regexp_replace(
                COALESCE(
                    r.payload->'raw'->>'price_rub',
                    r.payload->'raw'->>'price'
                ),
                '[^0-9]',
                '',
                'g'
            ),
            ''
        )::numeric                                        AS price_rub,

        r.parsed_at,
        r.payload
    FROM public.freights_ati_raw r
),
norm AS (
    SELECT
        s.*,

        -- distance может лежать:
        -- 1) payload->>'distance'        (если кто-то уже писал на верхнем уровне)
        -- 2) payload->'raw'->>'distance' (основной вариант от парсера)
        --
        -- Берём coalesce, потом проверяем, что там ТОЛЬКО цифры.
        CASE
            WHEN trim(
                     COALESCE(
                       s.payload->>'distance',
                       s.payload->'raw'->>'distance'
                     )
                 ) ~ '^[0-9]+$'
            THEN trim(
                     COALESCE(
                       s.payload->>'distance',
                       s.payload->'raw'->>'distance'
                     )
                 )::integer
            ELSE NULL
        END AS distance_km
    FROM src s
)
SELECT
    source,
    source_uid,
    hash,
    loading_city,
    unloading_city,
    cargo,
    body_type,
    loading_date,
    weight_t,
    volume_m3,
    price_rub,
    distance_km,
    parsed_at,
    payload
FROM norm;

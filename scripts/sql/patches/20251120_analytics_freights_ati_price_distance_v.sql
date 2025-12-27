-- scripts/sql/patches/20251120_analytics_freights_ati_price_distance_v.sql
--
-- Коридорная аналитика по ATI:
--
--  • источник: analytics.freights_ati_norm_v
--      (нормализованные веса/объёмы/цены/дистанции/города);
--  • уровень base:
--      считаем rub_per_km только для валидных distance_km > 0 и price_rub > 0;
--  • уровень agg:
--      агрегируем по (source, loading_city, unloading_city),
--      считаем:
--        - n_all / n_with_* / n_valid,
--        - средние price_rub / distance_km / rub_per_km,
--        - квантили RPM (p50 / p75 / p90).
--
-- Эта витрина используется как основа для:
--   • analytics.freights_ati_price_distance_mv (материализованная витрина);
--   • динамического RPM по направлениям (day/night quantiles).

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.freights_ati_price_distance_v AS
WITH base AS (
    SELECT
        source,
        loading_city,
        unloading_city,
        distance_km,
        price_rub,
        parsed_at::date AS d,
        CASE
            WHEN distance_km IS NOT NULL
                 AND distance_km > 0
                 AND price_rub IS NOT NULL
                 AND price_rub > 0
            THEN price_rub / distance_km::numeric
            ELSE NULL::numeric
        END AS rub_per_km
    FROM analytics.freights_ati_norm_v
),
agg AS (
    SELECT
        source,
        loading_city,
        unloading_city,
        MIN(d) AS first_date,
        MAX(d) AS last_date,

        -- Общее количество наблюдений по направлению
        COUNT(*) AS n_all,

        -- Сколько есть с валидной дистанцией
        COUNT(*) FILTER (
            WHERE distance_km IS NOT NULL
              AND distance_km > 0
        ) AS n_with_distance,

        -- Сколько есть с валидной ценой
        COUNT(*) FILTER (
            WHERE price_rub IS NOT NULL
              AND price_rub > 0
        ) AS n_with_price,

        -- Сколько наблюдений имеют валидный RPM (rub_per_km)
        COUNT(rub_per_km) AS n_valid,

        -- Средняя цена
        AVG(price_rub) FILTER (
            WHERE price_rub IS NOT NULL
              AND price_rub > 0
        ) AS avg_price_rub,

        -- Средняя дистанция
        AVG(distance_km) FILTER (
            WHERE distance_km IS NOT NULL
              AND distance_km > 0
        ) AS avg_distance_km,

        -- Средний RPM по валидным наблюдениям
        AVG(rub_per_km) AS avg_rub_per_km,

        -- Квантили RPM (rub_per_km) по направлению
        percentile_cont(0.5)  WITHIN GROUP (ORDER BY rub_per_km) AS p50_rub_per_km,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY rub_per_km) AS p75_rub_per_km,
        percentile_cont(0.9)  WITHIN GROUP (ORDER BY rub_per_km) AS p90_rub_per_km
    FROM base
    GROUP BY source, loading_city, unloading_city
)
SELECT
    source,
    loading_city,
    unloading_city,
    first_date,
    last_date,
    n_all,
    n_with_distance,
    n_with_price,
    n_valid,
    avg_price_rub,
    avg_distance_km,
    avg_rub_per_km,
    p50_rub_per_km,
    p75_rub_per_km,
    p90_rub_per_km
FROM agg;

-- scripts/sql/patches/20251120_analytics_freights_ati_price_distance_mv.sql
--
-- Материализованная витрина коридоров ATI:
--
--   Источник: analytics.freights_ati_price_distance_v
--     (агрегаты по (source, loading_city, unloading_city) с RPM-квантилами).
--
--   Назначение:
--     - быстрый доступ к рынку ATI по направлению (город–город);
--     - база для Dynamic RPM (floor/quantile) в автоплане;
--     - аналитические отчёты по рынку фрахта.
--
--   Обновление:
--     REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.freights_ati_price_distance_mv;
--
--   Связанные объекты:
--     - analytics.freights_ati_norm_v
--     - analytics.freights_ati_price_distance_v

CREATE SCHEMA IF NOT EXISTS analytics;

-- На всякий случай пересоздаём витрину (идемпотентно для патчей)
DROP MATERIALIZED VIEW IF EXISTS analytics.freights_ati_price_distance_mv;

CREATE MATERIALIZED VIEW analytics.freights_ati_price_distance_mv AS
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
FROM analytics.freights_ati_price_distance_v;

-- Уникальность по коридору в рамках источника (одна строка на (source, from, to))
CREATE UNIQUE INDEX IF NOT EXISTS idx_freights_ati_price_distance_mv_pk
    ON analytics.freights_ati_price_distance_mv (source, loading_city, unloading_city);

-- Быстрый поиск по направлению "откуда–куда"
CREATE INDEX IF NOT EXISTS idx_freights_ati_price_distance_mv_route
    ON analytics.freights_ati_price_distance_mv (loading_city, unloading_city);

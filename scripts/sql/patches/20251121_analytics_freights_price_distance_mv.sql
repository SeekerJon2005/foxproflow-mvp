-- scripts/sql/patches/20251121_analytics_freights_price_distance_mv.sql
--
-- Совместимая витрина analytics.freights_price_distance_mv.
--
-- Исторически в системе использовалась материализованная витрина
--   analytics.freights_price_distance_mv
-- без префикса источника.
--
-- После ввода новой витрины:
--   analytics.freights_ati_price_distance_mv
-- вся тяжёлая агрегация выполняется именно в ней.
--
-- Данный патч:
--   • гарантированно убирает старое MATERIALIZED VIEW (если было);
--   • создаёт обычный VIEW analytics.freights_price_distance_mv,
--     который прозрачно читает данные из analytics.freights_ati_price_distance_mv;
--   • сохраняет прежный набор колонок, чтобы старые запросы продолжали работать;
--   • идемпотентен и безопасен к повторному запуску.

CREATE SCHEMA IF NOT EXISTS analytics;

-- На всякий случай убираем старые артефакты с тем же именем.
-- Сначала MATERIALIZED VIEW, затем обычный VIEW — на случай смены типа.
DROP MATERIALIZED VIEW IF EXISTS analytics.freights_price_distance_mv;
DROP VIEW IF EXISTS analytics.freights_price_distance_mv;

-- Совместимый VIEW поверх новой витрины.
CREATE VIEW analytics.freights_price_distance_mv AS
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
FROM analytics.freights_ati_price_distance_mv;

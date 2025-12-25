-- 2025-11-19 — FoxProFlow
-- analytics.trips_route_gaps_v: дни с проблемным покрытием маршрутом.
-- NDC: только CREATE OR REPLACE VIEW поверх уже существующей витрины analytics.trips_daily_v.
-- Назначение:
--   - быстрый обзор качества маршрутизации по дням;
--   - явный статус покрытия (ok/warning/critical/unknown);
--   - удобный источник для KPI-агентов и алёртов.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.trips_route_gaps_v AS
SELECT
    d,
    trips_total,
    trips_with_route,
    trips_without_route,
    route_fill_rate_pct,

    -- "Дыра" в покрытии маршрутом: сколько % рейсов без маршрута
    CASE 
        WHEN route_fill_rate_pct IS NULL
            THEN NULL
        ELSE 100.0 - route_fill_rate_pct
    END                                             AS route_gap_pct,

    -- Статус покрытия:
    --   ok       — >= 95% рейсов с маршрутом;
    --   warning  — 80–95%;
    --   critical — < 80%;
    --   unknown  — нет данных по покрытию.
    CASE 
        WHEN route_fill_rate_pct IS NULL THEN 'unknown'
        WHEN route_fill_rate_pct >= 95.0 THEN 'ok'
        WHEN route_fill_rate_pct >= 80.0 THEN 'warning'
        ELSE 'critical'
    END                                             AS coverage_status
FROM analytics.trips_daily_v
WHERE trips_total > 0
ORDER BY d DESC;

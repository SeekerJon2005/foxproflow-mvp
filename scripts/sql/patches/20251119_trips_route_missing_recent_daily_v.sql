-- 2025-11-19 — FoxProFlow
-- analytics.trips_route_missing_recent_daily_v:
--   дневная сводка по рейсам за последние 7 дней, у которых есть сегменты без маршрута.
-- Источник: analytics.trips_route_missing_recent_v.
-- NDC: новый VIEW, существующие объекты не трогаем.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.trips_route_missing_recent_daily_v AS
SELECT
    d,
    COUNT(*)                            AS trips_with_missing_route,
    SUM(segments_total)                 AS segments_total,
    SUM(segments_without_route)         AS segments_without_route,
    CASE
        WHEN SUM(segments_total) > 0
        THEN 100.0 * SUM(segments_without_route)::numeric / SUM(segments_total)::numeric
        ELSE NULL
    END                                 AS segments_missing_pct
FROM analytics.trips_route_missing_recent_v
GROUP BY d
ORDER BY d DESC;

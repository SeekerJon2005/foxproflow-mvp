-- 2025-11-19 — FoxProFlow
-- analytics.trips_route_gaps_recent_v: последние дни с проблемным покрытием маршрутом.
-- NDC: только CREATE OR REPLACE VIEW поверх analytics.trips_route_gaps_v.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.trips_route_gaps_recent_v AS
SELECT
    d,
    trips_total,
    trips_with_route,
    trips_without_route,
    route_fill_rate_pct,
    route_gap_pct,
    coverage_status
FROM analytics.trips_route_gaps_v
WHERE d >= current_date - INTERVAL '7 days'
  AND trips_total > 0
ORDER BY d DESC;

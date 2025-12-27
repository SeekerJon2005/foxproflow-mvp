-- 2025-11-19 — FoxProFlow
-- analytics.trips_route_missing_recent_v:
--   рейсы за последние 7 дней, у которых не все сегменты имеют рассчитанный маршрут (road_km).
-- NDC: новый VIEW, существующие объекты не трогаем.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.trips_route_missing_recent_v AS
WITH seg AS (
    SELECT
        s.trip_id,
        COUNT(*)                                       AS segments_total,
        COUNT(*) FILTER (WHERE s.road_km IS NOT NULL) AS segments_with_route,
        COUNT(*) FILTER (WHERE s.road_km IS NULL)     AS segments_without_route
    FROM public.trip_segments s
    GROUP BY s.trip_id
),
base AS (
    SELECT
        t.id                                          AS trip_id,
        t.status                                      AS status,
        COALESCE(t.confirmed_at, t.created_at)        AS ts,
        date_trunc('day', COALESCE(t.confirmed_at, t.created_at))::date AS d,
        seg.segments_total,
        seg.segments_with_route,
        seg.segments_without_route,
        CASE 
            WHEN seg.segments_total > 0
            THEN 100.0 * seg.segments_with_route::numeric / seg.segments_total::numeric
            ELSE NULL
        END                                           AS route_fill_rate_pct_trip
    FROM public.trips t
    LEFT JOIN seg ON seg.trip_id = t.id
    WHERE t.status = 'confirmed'
      AND COALESCE(t.confirmed_at, t.created_at) >= current_date - INTERVAL '7 days'
)
SELECT
    trip_id,
    status,
    ts,
    d,
    segments_total,
    segments_with_route,
    segments_without_route,
    route_fill_rate_pct_trip
FROM base
WHERE segments_without_route > 0
ORDER BY d DESC, trip_id;

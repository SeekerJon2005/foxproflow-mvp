-- 2025-11-24 — FoxProFlow
-- Базовая дневная витрина по рейсам + stub trips_with_route и route_fill_rate_pct.
-- NDC: CREATE SCHEMA IF NOT EXISTS + DROP VIEW IF EXISTS + CREATE VIEW.

CREATE SCHEMA IF NOT EXISTS analytics;

DROP VIEW IF EXISTS analytics.trips_daily_v;

CREATE VIEW analytics.trips_daily_v AS
WITH src AS (
    SELECT
        date_trunc('day', t.created_at)::date AS d,
        t.status
    FROM public.trips t
),
agg AS (
    SELECT
        d,
        count(*)::int AS trips_total,
        -- stub: пока считаем, что у всех рейсов есть маршрут.
        count(*)::int AS trips_with_route,
        count(*) FILTER (WHERE status = 'confirmed')::int AS trips_confirmed,
        count(*) FILTER (WHERE status = 'planned')::int   AS trips_planned,
        count(*) FILTER (WHERE status = 'cancelled')::int AS trips_cancelled
    FROM src
    GROUP BY d
)
SELECT
    d,
    trips_total,
    trips_with_route,
    -- 100% * (рейсы с маршрутом / все рейсы), с защитой от деления на ноль
    CASE
        WHEN trips_total > 0
        THEN (trips_with_route::numeric * 100.0) / trips_total::numeric
        ELSE NULL
    END AS route_fill_rate_pct,
    trips_confirmed,
    trips_planned,
    trips_cancelled
FROM agg
ORDER BY d;

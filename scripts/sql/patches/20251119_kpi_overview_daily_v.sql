-- 2025-11-19 — FoxProFlow
-- analytics.kpi_overview_daily_v: сводный дневной KPI по системе.
-- Источники:
--   - analytics.trips_daily_v                      (рейсы, выручка, RPM/RPH);
--   - analytics.trips_route_gaps_v                (покрытие маршрутом, статус);
--   - analytics.trips_route_missing_recent_daily_v (кол-во рейсов/сегментов без маршрута, последние 7 дней);
--   - analytics.autoplan_daily_v                  (активность автоплана по дням).
-- NDC: новый VIEW, существующие объекты не трогаем.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.kpi_overview_daily_v AS
SELECT
    t.d                                           AS d,

    -- Рейсы
    t.trips_total,
    t.trips_with_route,
    t.trips_without_route,
    t.revenue_plan_rub,
    t.total_route_km,
    t.total_drive_hours,
    t.rpm_plan,
    t.rph_plan,

    -- Покрытие маршрутом по дням (из gaps-витрины)
    g.route_fill_rate_pct                        AS route_fill_rate_pct,
    g.route_gap_pct                              AS route_gap_pct,
    g.coverage_status                            AS route_coverage_status,

    -- Сводка по рейсам с отсутствующим маршрутом (за последние 7 дней может быть NULL для старых дат)
    m.trips_with_missing_route,
    m.segments_total                             AS missing_segments_total,
    m.segments_without_route                     AS missing_segments_without_route,
    m.segments_missing_pct,

    -- Активность автоплана
    a.runs_total                                 AS autoplan_runs_total
FROM analytics.trips_daily_v t
LEFT JOIN analytics.trips_route_gaps_v g
       ON g.d = t.d
LEFT JOIN analytics.trips_route_missing_recent_daily_v m
       ON m.d = t.d
LEFT JOIN analytics.autoplan_daily_v a
       ON a.d = t.d
ORDER BY t.d DESC;

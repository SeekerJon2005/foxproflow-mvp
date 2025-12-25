-- 2025-11-19 — FoxProFlow
-- analytics.trips_monthly_ext_v: расширенная месячная витрина по рейсам.
-- Источники:
--   - analytics.trips_daily_v (выручка, RPM/RPH);
--   - analytics.trips_route_gaps_v (покрытие маршрутом).
-- NDC: новый VIEW, существующие объекты не трогаем.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.trips_monthly_ext_v AS
WITH daily AS (
    SELECT
        d.d::date                                    AS day,
        date_trunc('month', d.d)::date               AS month,
        d.trips_total,
        d.trips_with_route,
        d.trips_without_route,
        d.revenue_plan_rub,
        d.rpm_plan,
        d.rph_plan,
        g.route_fill_rate_pct,
        g.route_gap_pct,
        g.coverage_status
    FROM analytics.trips_daily_v d
    JOIN analytics.trips_route_gaps_v g
      ON g.d = d.d
)
SELECT
    month,

    COUNT(*)                                        AS days_with_data,

    SUM(trips_total)                                AS trips_total,
    SUM(trips_with_route)                           AS trips_with_route,
    SUM(trips_without_route)                        AS trips_without_route,

    -- Среднее, минимум и максимум покрытия маршрутом по дням
    AVG(route_fill_rate_pct)                        AS route_fill_rate_pct_avg,
    MIN(route_fill_rate_pct)                        AS route_fill_rate_pct_min,
    MAX(route_fill_rate_pct)                        AS route_fill_rate_pct_max,

    -- Суммарная плановая выручка за месяц
    SUM(revenue_plan_rub)                           AS revenue_plan_rub,

    -- Средний плановый RPM/RPH по дням (простое среднее дневных метрик)
    AVG(rpm_plan)                                   AS rpm_plan_avg,
    AVG(rph_plan)                                   AS rph_plan_avg,

    -- Доли дней по статусам покрытия
    AVG(CASE WHEN coverage_status = 'ok'       THEN 1.0 ELSE 0.0 END) * 100.0 AS days_ok_pct,
    AVG(CASE WHEN coverage_status = 'warning'  THEN 1.0 ELSE 0.0 END) * 100.0 AS days_warning_pct,
    AVG(CASE WHEN coverage_status = 'critical' THEN 1.0 ELSE 0.0 END) * 100.0 AS days_critical_pct
FROM daily
GROUP BY month
ORDER BY month DESC;

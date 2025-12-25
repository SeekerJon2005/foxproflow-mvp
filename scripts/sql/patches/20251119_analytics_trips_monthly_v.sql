-- file: scripts/sql/patches/20251119_analytics_trips_monthly_v.sql
--
-- Месячная аналитическая витрина по рейсам.
-- Сводит данные из analytics.trips_daily_v в месяцы:
--   • количество рейсов,
--   • доля рейсов с маршрутом,
--   • суммарная плановая выручка,
--   • средний RPM.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.trips_monthly_v AS
SELECT
  date_trunc('month', d)::date                      AS month,
  sum(trips_total)                                  AS trips_total,
  sum(trips_with_route)                             AS trips_with_route,
  sum(trips_without_route)                          AS trips_without_route,
  CASE
    WHEN sum(trips_total) > 0
    THEN sum(trips_with_route)::numeric / sum(trips_total)
    ELSE NULL
  END                                               AS pct_with_route,
  sum(revenue_plan_rub)                             AS revenue_plan_rub,
  avg(rpm_actual_avg)                               AS rpm_actual_avg
FROM analytics.trips_daily_v
GROUP BY date_trunc('month', d);

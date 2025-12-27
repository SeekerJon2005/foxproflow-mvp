-- 2025-11-19 — FoxProFlow
-- analytics.trips_daily_v: дневная витрина по рейсам.
-- NDC: только CREATE SCHEMA IF NOT EXISTS + CREATE OR REPLACE VIEW.
--
-- Назначение:
--   • дневные агрегаты по confirmed-рейсам;
--   • покрытие маршрутом (сколько рейсов имеют route_km/drive_sec);
--   • плановая выручка по trips.price_rub_plan;
--   • средние RPM/RPH на базе плановой цены и километража.
--
-- ВАЖНО: первые 8 колонок совместимы с исходной схемой:
--   d, trips_total, trips_with_route, trips_without_route,
--   revenue_plan_rub, rpm_actual_avg, rpm_actual_avg_routed, rpm_actual_avg_unrouted.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.trips_daily_v AS
WITH base AS (
    SELECT
        -- День считаем по дате подтверждения, fallback на created_at
        date_trunc('day', COALESCE(t.confirmed_at, t.created_at))::date AS d,
        t.id                                   AS trip_id,
        t.status                               AS status,
        COALESCE(t.price_rub_plan, 0)::numeric AS price_rub_plan,
        SUM(s.road_km)                         AS route_km,
        SUM(s.drive_sec)                       AS drive_sec
    FROM public.trips t
    LEFT JOIN public.trip_segments s
           ON s.trip_id = t.id
    WHERE t.status = 'confirmed'
    GROUP BY 1,2,3,4
)
SELECT
    -- ПЕРВЫЕ 8 КОЛОНОК: как в исходной витрине
    b.d                                            AS d,
    COUNT(*)                                       AS trips_total,
    COUNT(*) FILTER (WHERE b.route_km IS NOT NULL) AS trips_with_route,
    COUNT(*) FILTER (WHERE b.route_km IS NULL)     AS trips_without_route,
    SUM(b.price_rub_plan)                          AS revenue_plan_rub,

    -- Средняя RPM по всем рейсам (по плановой цене и фактическому км)
    CASE
        WHEN SUM(COALESCE(b.route_km, 0)) > 0
        THEN SUM(b.price_rub_plan)
             / NULLIF(SUM(COALESCE(b.route_km, 0)), 0)
        ELSE NULL
    END                                           AS rpm_actual_avg,

    -- Средняя RPM только по рейсам с маршрутом
    CASE
        WHEN SUM(COALESCE(b.route_km, 0)) FILTER (WHERE b.route_km IS NOT NULL) > 0
        THEN SUM(b.price_rub_plan) FILTER (WHERE b.route_km IS NOT NULL)
             / NULLIF(
                 SUM(COALESCE(b.route_km, 0)) FILTER (WHERE b.route_km IS NOT NULL),
                 0
               )
        ELSE NULL
    END                                           AS rpm_actual_avg_routed,

    -- RPM по нерутированным рейсам не считаем (нет километража)
    NULL::numeric                                 AS rpm_actual_avg_unrouted,

    -- ДОПОЛНИТЕЛЬНЫЕ КОЛОНКИ

    -- Доля рейсов с маршрутом, %
    CASE 
        WHEN COUNT(*) > 0
        THEN 100.0
             * COUNT(*) FILTER (WHERE b.route_km IS NOT NULL)
             / COUNT(*)
        ELSE NULL
    END                                           AS route_fill_rate_pct,

    -- Суммарный километраж и часы в пути
    SUM(COALESCE(b.route_km, 0))                  AS total_route_km,
    (SUM(COALESCE(b.drive_sec, 0)) / 3600.0)      AS total_drive_hours,

    -- Плановая RPM (то же, что rpm_actual_avg, но отдельно для читаемости)
    CASE 
        WHEN SUM(COALESCE(b.route_km, 0)) > 0
        THEN SUM(b.price_rub_plan)
             / NULLIF(SUM(COALESCE(b.route_km, 0)), 0)
        ELSE NULL
    END                                           AS rpm_plan,

    -- Плановая RPH (выручка в час в пути)
    CASE 
        WHEN SUM(COALESCE(b.drive_sec, 0)) > 0
        THEN SUM(b.price_rub_plan)
             / NULLIF((SUM(COALESCE(b.drive_sec, 0)) / 3600.0), 0)
        ELSE NULL
    END                                           AS rph_plan
FROM base b
GROUP BY b.d
ORDER BY b.d DESC;

-- scripts/sql/patches/20251126_analytics_driver_trip_monitor.sql
-- Витрина для мониторинга рейсов водителей:
--  - последний статус рейса
--  - origin/dest регион
--  - водитель и машина
--  - последняя точка телеметрии
--  - последний off-route alert (если есть)
--  - driver_ack_at / completed_at для понимания стадии рейса

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.driver_trip_monitor_v AS
WITH last_telemetry AS (
    SELECT DISTINCT ON (dt.trip_id)
        dt.trip_id,
        dt.driver_id,
        dt.truck_id,
        dt.ts      AS last_ts,
        dt.lat     AS last_lat,
        dt.lon     AS last_lon,
        dt.speed_kph
    FROM public.driver_telemetry dt
    ORDER BY dt.trip_id, dt.ts DESC
),
last_alert AS (
    SELECT DISTINCT ON (a.trip_id)
        a.trip_id,
        a.ts      AS alert_ts,
        a.level   AS alert_level,
        a.alert_type,
        (a.details->>'detour_factor')::numeric AS detour_factor
    FROM ops.driver_alerts a
    ORDER BY a.trip_id, a.ts DESC
)
SELECT
    t.id                          AS trip_id,
    t.status,
    t.loading_region              AS loading_region,
    t.unloading_region            AS unloading_region,
    COALESCE(t.meta->'autoplan'->>'o', t.loading_region)   AS origin_region,
    COALESCE(t.meta->'autoplan'->>'d', t.unloading_region) AS dest_region,

    tr.id                         AS truck_id,
    tr.driver_id,
    d.phone                       AS driver_phone,
    d.full_name                   AS driver_name,

    -- дополнительные поля по рейсу
    t.driver_ack_at,
    t.completed_at,

    -- последняя телеметрия
    lt.last_ts,
    lt.last_lat,
    lt.last_lon,
    lt.speed_kph,

    -- последний off-route alert (если есть)
    la.alert_ts,
    la.alert_level,
    la.alert_type,
    la.detour_factor
FROM public.trips t
JOIN public.trucks tr
  ON tr.id = t.truck_id
LEFT JOIN public.drivers d
  ON d.id = tr.driver_id
LEFT JOIN last_telemetry lt
  ON lt.trip_id = t.id
LEFT JOIN last_alert la
  ON la.trip_id = t.id
WHERE t.status IN ('planned','confirmed');

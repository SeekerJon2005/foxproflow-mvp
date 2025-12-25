-- 20251126_analytics_driver_trip_monitor_resolved.sql
--
-- Обновление витрины мониторинга рейсов водителей:
--   • last_alert теперь учитывает только НЕ закрытые алерты (resolved_at IS NULL);
--   • закрытые алерты остаются в ops.driver_alerts для истории и аудита,
--     но не попадают в /api/dispatcher/trips/monitor (off-route мониторинг).
--
-- Патч недеструктивный: таблицы не трогаем, только CREATE OR REPLACE VIEW.

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
    WHERE a.resolved_at IS NULL
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

    t.driver_ack_at,
    t.completed_at,

    lt.last_ts,
    lt.last_lat,
    lt.last_lon,
    lt.speed_kph,

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
WHERE t.status IN ('planned', 'confirmed');

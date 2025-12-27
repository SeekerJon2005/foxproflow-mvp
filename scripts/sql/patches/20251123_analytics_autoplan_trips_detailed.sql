CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.autoplan_trips_detailed_v AS
SELECT
    t.id    AS trip_id,
    t.status,
    t.created_at,
    t.confirmed_at,
    COALESCE(a.plan_name, a.thresholds->>'flow_plan', 'unknown') AS flow_plan,

    -- из метаданных автоплана в trips.meta->'autoplan'
    (t.meta->'autoplan'->>'freight_id')::bigint AS freight_id,

    f.loading_region,
    f.unloading_region,
    f.loading_date,

    COALESCE(SUM(s.price_rub), 0) AS trip_price_rub
FROM public.trips t
JOIN public.autoplan_audit a
  ON a.trip_id = t.id
 AND a.decision = 'confirm'
 AND a.applied IS TRUE
LEFT JOIN public.trip_segments s
  ON s.trip_id = t.id
LEFT JOIN public.freights f
  ON f.id = (t.meta->'autoplan'->>'freight_id')::bigint
WHERE t.status = 'confirmed'
GROUP BY
    t.id,
    t.status,
    t.created_at,
    t.confirmed_at,
    COALESCE(a.plan_name, a.thresholds->>'flow_plan', 'unknown'),
    (t.meta->'autoplan'->>'freight_id')::bigint,
    f.loading_region,
    f.unloading_region,
    f.loading_date;

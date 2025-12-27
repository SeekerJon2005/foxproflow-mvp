BEGIN;

CREATE OR REPLACE VIEW public.trips_recent_v AS
WITH seg AS (
    SELECT
        ts.trip_id,
        MIN(ts.origin_region) AS origin_region,
        MIN(ts.dest_region)   AS dest_region,
        SUM(ts.road_km)       AS road_km,
        SUM(ts.drive_sec)     AS drive_sec
    FROM public.trip_segments ts
    GROUP BY ts.trip_id
)
SELECT
    t.id,
    t.status,
    t.created_at,
    t.confirmed_at,
    COALESCE(
        seg.origin_region,
        (t.meta->'autoplan'->>'o')
    ) AS origin_region,
    COALESCE(
        seg.dest_region,
        (t.meta->'autoplan'->>'d')
    ) AS dest_region,
    (t.meta->'autoplan'->>'price')::numeric AS price_rub,
    seg.road_km,
    seg.drive_sec
FROM public.trips t
LEFT JOIN seg
    ON seg.trip_id = t.id
WHERE t.status = 'confirmed';

COMMIT;

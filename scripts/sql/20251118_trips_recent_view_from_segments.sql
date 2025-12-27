BEGIN;

-- Обновляем витрину recent-рейсов так, чтобы origin/dest и метрики
-- брались из trip_segments, а цена — из meta.autoplan.price.

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
    -- регионы и метрики — из сегментов
    seg.origin_region,
    seg.dest_region,
    -- цену берём из meta.autoplan.price
    (t.meta->'autoplan'->>'price')::numeric AS price_rub,
    seg.road_km,
    seg.drive_sec
FROM public.trips t
LEFT JOIN seg
       ON seg.trip_id = t.id
WHERE t.status = 'confirmed';

COMMIT;

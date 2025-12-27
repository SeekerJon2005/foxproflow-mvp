BEGIN;

-- 1) Для всех confirmed-рейсов без сегментов создаём по одному сегменту
--    на основе meta.autoplan (o = origin_region, d = dest_region).
--    km / sec пока NULL — их добьёт routing.enrich.trips.
--    Скрипт идемпотентен: повторный запуск не создаст дубликатов.

WITH candidates AS (
    SELECT
        t.id                                         AS trip_id,
        (t.meta->'autoplan'->>'o')                   AS origin_region,
        (t.meta->'autoplan'->>'d')                   AS dest_region
    FROM public.trips t
    LEFT JOIN public.trip_segments s
           ON s.trip_id = t.id
    WHERE t.status = 'confirmed'
      AND s.trip_id IS NULL              -- нет ни одного сегмента по этому trip_id
      AND t.meta ? 'autoplan'            -- есть блок meta.autoplan
      AND t.meta->'autoplan'->>'o' IS NOT NULL
      AND t.meta->'autoplan'->>'d' IS NOT NULL
)

INSERT INTO public.trip_segments (
    trip_id,
    segment_order,
    origin_region,
    dest_region,
    road_km,
    drive_sec
)
SELECT
    c.trip_id,
    1                                      AS segment_order,
    c.origin_region,
    c.dest_region,
    NULL::numeric                          AS road_km,
    NULL::integer                          AS drive_sec
FROM candidates c;

COMMIT;

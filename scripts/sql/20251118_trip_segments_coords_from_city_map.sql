BEGIN;

-- 1) Заполняем координаты погрузки (src_lat/src_lon) по origin_region через city_map
-- Используем два варианта матчинга:
--   a) fn_norm_key(origin_region) = norm_key(name)      (основной сценарий)
--   b) fn_norm_key(origin_region) = fn_norm_key(region) (наследие старой схемы)
-- Берём только записи city_map, у которых есть lat/lon.

WITH src_candidates AS (
    SELECT
        ts.origin_region,
        cm.lat,
        cm.lon,
        -- 2 = совпало по name (norm_key), 1 = совпало по region, 0 = не должно случаться
        CASE
            WHEN cm.norm_key = fn_norm_key(ts.origin_region) THEN 2
            WHEN fn_norm_key(cm.region) = fn_norm_key(ts.origin_region) THEN 1
            ELSE 0
        END AS match_score,
        row_number() OVER (
            PARTITION BY ts.origin_region
            ORDER BY
                CASE
                    WHEN cm.norm_key = fn_norm_key(ts.origin_region) THEN 2
                    WHEN fn_norm_key(cm.region) = fn_norm_key(ts.origin_region) THEN 1
                    ELSE 0
                END DESC,
                CASE cm.source
                    WHEN 'yandex'  THEN 3
                    WHEN 'import'  THEN 2
                    WHEN 'suggest' THEN 1
                    ELSE 0
                END DESC,
                cm.updated_at DESC,
                cm.id ASC
        ) AS rn
    FROM public.trip_segments ts
    JOIN public.city_map cm
      ON (
           cm.norm_key = fn_norm_key(ts.origin_region)
        OR fn_norm_key(cm.region) = fn_norm_key(ts.origin_region)
      )
    WHERE
        (ts.src_lat IS NULL OR ts.src_lon IS NULL)
        AND ts.origin_region IS NOT NULL
        AND ts.origin_region <> ''
        AND cm.lat IS NOT NULL
        AND cm.lon IS NOT NULL
),
src_best AS (
    SELECT origin_region, lat, lon
    FROM src_candidates
    WHERE rn = 1
),
src_upd AS (
    UPDATE public.trip_segments ts
    SET
        src_lat = sb.lat,
        src_lon = sb.lon
    FROM src_best sb
    WHERE
        ts.origin_region = sb.origin_region
        AND (ts.src_lat IS NULL OR ts.src_lon IS NULL)
    RETURNING 1
)
SELECT count(*) AS src_updated
FROM src_upd;

-- 2) Заполняем координаты выгрузки (dst_lat/dst_lon) по dest_region через city_map
-- Логика аналогична пункту (1).

WITH dst_candidates AS (
    SELECT
        ts.dest_region,
        cm.lat,
        cm.lon,
        CASE
            WHEN cm.norm_key = fn_norm_key(ts.dest_region) THEN 2
            WHEN fn_norm_key(cm.region) = fn_norm_key(ts.dest_region) THEN 1
            ELSE 0
        END AS match_score,
        row_number() OVER (
            PARTITION BY ts.dest_region
            ORDER BY
                CASE
                    WHEN cm.norm_key = fn_norm_key(ts.dest_region) THEN 2
                    WHEN fn_norm_key(cm.region) = fn_norm_key(ts.dest_region) THEN 1
                    ELSE 0
                END DESC,
                CASE cm.source
                    WHEN 'yandex'  THEN 3
                    WHEN 'import'  THEN 2
                    WHEN 'suggest' THEN 1
                    ELSE 0
                END DESC,
                cm.updated_at DESC,
                cm.id ASC
        ) AS rn
    FROM public.trip_segments ts
    JOIN public.city_map cm
      ON (
           cm.norm_key = fn_norm_key(ts.dest_region)
        OR fn_norm_key(cm.region) = fn_norm_key(ts.dest_region)
      )
    WHERE
        (ts.dst_lat IS NULL OR ts.dst_lon IS NULL)
        AND ts.dest_region IS NOT NULL
        AND ts.dest_region <> ''
        AND cm.lat IS NOT NULL
        AND cm.lon IS NOT NULL
),
dst_best AS (
    SELECT dest_region, lat, lon
    FROM dst_candidates
    WHERE rn = 1
),
dst_upd AS (
    UPDATE public.trip_segments ts
    SET
        dst_lat = db.lat,
        dst_lon = db.lon
    FROM dst_best db
    WHERE
        ts.dest_region = db.dest_region
        AND (ts.dst_lat IS NULL OR ts.dst_lon IS NULL)
    RETURNING 1
)
SELECT count(*) AS dst_updated
FROM dst_upd;

-- 3) Диагностика: сколько сегментов за последние 5 дней осталось без координат

SELECT
  date(t.created_at) AS d,
  COUNT(*) FILTER (WHERE ts.src_lat IS NOT NULL AND ts.dst_lat IS NOT NULL) AS both_coords,
  COUNT(*) FILTER (WHERE ts.src_lat IS NOT NULL AND ts.dst_lat IS NULL)     AS only_src,
  COUNT(*) FILTER (WHERE ts.src_lat IS NULL AND ts.dst_lat IS NOT NULL)     AS only_dst,
  COUNT(*) FILTER (WHERE ts.src_lat IS NULL AND ts.dst_lat IS NULL)         AS none_coords
FROM public.trips t
JOIN public.trip_segments ts ON ts.trip_id = t.id
WHERE t.created_at >= now() - interval '5 days'
GROUP BY date(t.created_at)
ORDER BY d DESC;

COMMIT;

-- 2025-11-15 — FoxProFlow
-- Backfill регионов в trips из freights_enriched_mv по freight_id.
--
-- Цель:
--   • для рейсов с пустыми / 'RU-UNK' регионами попытаться
--     аккуратно проставить loading_region / unloading_region
--     по данным freights_enriched_mv.
--
-- Гарантии:
--   • не трогаем уже нормальные регионы;
--   • не заливаем 'RU-UNK';
--   • скрипт идемпотентен.

BEGIN;

WITH fe_join AS (
    -- Связываем freights_enriched_mv с исходной таблицей freights по source_uid
    -- и берём оттуда реальный freight_id (freights.id).
    SELECT
        fr.id                AS freight_id,
        to_jsonb(fe)         AS j
    FROM public.freights fr
    JOIN public.freights_enriched_mv fe
      ON to_jsonb(fe)->>'source_uid' = fr.source_uid
),
f_norm AS (
    -- Нормализуем регионы из витрины:
    -- пробуем несколько возможных полей, приводим к верхнему регистру,
    -- отбрасываем пустые строки.
    SELECT
        freight_id,

        UPPER(
          NULLIF(
            COALESCE(
              j->>'loading_region_code',
              j->>'loading_region_iso',
              j->>'loading_region',
              j->>'loading_region_norm'
            ),
            ''
          )
        ) AS origin_region,

        UPPER(
          NULLIF(
            COALESCE(
              j->>'unloading_region_code',
              j->>'unloading_region_iso',
              j->>'unloading_region',
              j->>'unloading_region_norm'
            ),
            ''
          )
        ) AS dest_region
    FROM fe_join
),
f_good AS (
    -- Берём только те строки, где регионы реально нормальные,
    -- а не NULL/пусто/RU-UNK.
    SELECT *
    FROM f_norm
    WHERE origin_region IS NOT NULL
      AND dest_region IS NOT NULL
      AND origin_region <> 'RU-UNK'
      AND dest_region <> 'RU-UNK'
)
UPDATE public.trips t
SET
    loading_region   = fg.origin_region,
    unloading_region = fg.dest_region
FROM f_good fg
WHERE
    -- связь trips → freights по freight_id в meta.autoplan
    (t.meta->'autoplan'->>'freight_id')::bigint = fg.freight_id
    -- обновляем только «плохие» регионы
    AND (
        t.loading_region IS NULL
        OR t.loading_region = ''
        OR t.loading_region = 'RU-UNK'
    )
    AND (
        t.unloading_region IS NULL
        OR t.unloading_region = ''
        OR t.unloading_region = 'RU-UNK'
    );

COMMIT;

-- При необходимости можно посмотреть, сколько строк ещё в RU-UNK:
--
--   SELECT
--     COUNT(*) FILTER (
--       WHERE loading_region IS NULL
--          OR loading_region = ''
--          OR loading_region = 'RU-UNK'
--          OR unloading_region IS NULL
--          OR unloading_region = ''
--          OR unloading_region = 'RU-UNK'
--     ) AS trips_bad,
--     COUNT(*) AS trips_total
--   FROM public.trips;

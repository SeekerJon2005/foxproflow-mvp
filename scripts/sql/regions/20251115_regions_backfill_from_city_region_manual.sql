-- 2025-11-15 — FoxProFlow
-- Backfill регионов в trips на основе справочника city_region_manual.
--
-- Цель:
--   • для рейсов с пустыми / 'RU-UNK' регионами попытаться
--     проставить loading_region / unloading_region по city_region_manual,
--     используя сырые города/регионы из freights_enriched_mv.
--
-- Гарантии:
--   • обновляем только "плохие" регионы;
--   • используем только записи, где region_code IS NOT NULL;
--   • скрипт идемпотентен.

BEGIN;

WITH unk_trips AS (
    SELECT
        t.id AS trip_id,
        (t.meta->'autoplan'->>'freight_id')::bigint AS freight_id
    FROM public.trips t
    WHERE
        (t.loading_region IS NULL
         OR t.loading_region = ''
         OR t.loading_region = 'RU-UNK')
        AND
        (t.unloading_region IS NULL
         OR t.unloading_region = ''
         OR t.unloading_region = 'RU-UNK')
),
fe_join AS (
    SELECT
        u.trip_id,
        u.freight_id,
        fr.source_uid AS freight_source_uid,
        to_jsonb(fe)  AS j
    FROM unk_trips u
    LEFT JOIN public.freights fr
      ON fr.id = u.freight_id
    LEFT JOIN public.freights_enriched_mv fe
      ON to_jsonb(fe)->>'source_uid' = fr.source_uid
),
norm AS (
    SELECT
        trip_id,
        freight_id,
        NULLIF(j->>'loading_city','')   AS load_city,
        NULLIF(j->>'loading_region','') AS load_region_raw,
        NULLIF(j->>'unloading_city','')   AS unload_city,
        NULLIF(j->>'unloading_region','') AS unload_region_raw
    FROM fe_join
),
joined AS (
    SELECT
        n.trip_id,
        n.freight_id,
        cm_load.region_code   AS load_region_code,
        cm_unload.region_code AS unload_region_code
    FROM norm n
    LEFT JOIN public.city_region_manual cm_load
      ON COALESCE(cm_load.raw_city,'')  = COALESCE(n.load_city,'')
     AND COALESCE(cm_load.raw_region,'')= COALESCE(n.load_region_raw,'')
     AND cm_load.region_code IS NOT NULL
    LEFT JOIN public.city_region_manual cm_unload
      ON COALESCE(cm_unload.raw_city,'')  = COALESCE(n.unload_city,'')
     AND COALESCE(cm_unload.raw_region,'')= COALESCE(n.unload_region_raw,'')
     AND cm_unload.region_code IS NOT NULL
)
UPDATE public.trips t
SET
    loading_region = COALESCE(t.loading_region, j.load_region_code),
    unloading_region = COALESCE(t.unloading_region, j.unload_region_code)
FROM joined j
WHERE
    t.id = j.trip_id
    AND (
        t.loading_region IS NULL
        OR t.loading_region = ''
        OR t.loading_region = 'RU-UNK'
    )
    AND (
        t.unloading_region IS NULL
        OR t.unloading_region = ''
        OR t.unloading_region = 'RU-UNK'
    )
    AND (
        j.load_region_code IS NOT NULL
        OR j.unload_region_code IS NOT NULL
    );

COMMIT;

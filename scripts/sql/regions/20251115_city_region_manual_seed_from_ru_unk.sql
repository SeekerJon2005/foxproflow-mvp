-- 2025-11-15 — FoxProFlow
-- Первичное наполнение city_region_manual на основе рейсов с RU-UNK.

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
raw_pairs AS (
    SELECT DISTINCT
        NULLIF(j->>'loading_city','')   AS raw_city,
        NULLIF(j->>'loading_region','') AS raw_region
    FROM fe_join
)
INSERT INTO public.city_region_manual (raw_city, raw_region, region_code, source)
SELECT
    rp.raw_city,
    rp.raw_region,
    NULL::text     AS region_code,
    'trips_ru_unk' AS source
FROM raw_pairs rp
WHERE
    (rp.raw_city IS NOT NULL OR rp.raw_region IS NOT NULL)
    AND NOT EXISTS (
        SELECT 1
        FROM public.city_region_manual m
        WHERE
            COALESCE(m.raw_city,'')  = COALESCE(rp.raw_city,'')
        AND COALESCE(m.raw_region,'')= COALESCE(rp.raw_region,'')
    );

COMMIT;

-- 2025-11-15 — FoxProFlow
-- Backfill регионов в trips из meta->'autoplan'
-- Идея: аккуратно проставить loading_region / unloading_region
-- там, где они пустые или равны 'RU-UNK', используя meta.autoplan.o/d.

BEGIN;

UPDATE public.trips t
SET
    loading_region   = COALESCE(
        NULLIF(loading_region, ''),
        NULLIF(t.meta->'autoplan'->>'o','')
    ),
    unloading_region = COALESCE(
        NULLIF(unloading_region, ''),
        NULLIF(t.meta->'autoplan'->>'d','')
    )
WHERE
    (
        loading_region IS NULL
        OR loading_region = ''
        OR loading_region = 'RU-UNK'
    )
    OR
    (
        unloading_region IS NULL
        OR unloading_region = ''
        OR unloading_region = 'RU-UNK'
    );

COMMIT;

-- Диагностику лучше запускать отдельным SELECT из PowerShell:
--   SELECT loading_region, unloading_region, COUNT(*)
--   FROM public.trips
--   GROUP BY loading_region, unloading_region
--   ORDER BY trips_count DESC
--   LIMIT 50;

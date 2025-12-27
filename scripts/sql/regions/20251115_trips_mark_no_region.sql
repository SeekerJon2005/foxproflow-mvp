-- 2025-11-15 — FoxProFlow
-- Пометка рейсов без регионов (RU-UNK/пусто) как "invalid" для автоплана.

BEGIN;

UPDATE public.trips t
SET
    status = 'invalid',
    meta = jsonb_set(
        COALESCE(meta, '{}'::jsonb),
        '{autoplan,skip_reason}',
        to_jsonb('no_region'::text),
        true
    )
WHERE
    -- регионы отсутствуют или RU-UNK
    (t.loading_region IS NULL
     OR t.loading_region = ''
     OR t.loading_region = 'RU-UNK')
    AND
    (t.unloading_region IS NULL
     OR t.unloading_region = ''
     OR t.unloading_region = 'RU-UNK')
    -- это именно автоплановские рейсы (есть freight_id в meta.autoplan)
    AND (t.meta->'autoplan'->>'freight_id') IS NOT NULL;

COMMIT;

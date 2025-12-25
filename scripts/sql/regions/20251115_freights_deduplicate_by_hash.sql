-- 2025-11-15 — FoxProFlow
-- Одноразовая чистка дублей в freights по hash.

BEGIN;

WITH ranked AS (
    SELECT
        id,
        hash,
        parsed_at,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY hash
            ORDER BY
                parsed_at DESC NULLS LAST,
                created_at DESC NULLS LAST,
                id DESC
        ) AS rn
    FROM public.freights
    WHERE hash IS NOT NULL
)
DELETE FROM public.freights f
USING ranked r
WHERE f.id = r.id
  AND r.rn > 1;

COMMIT;

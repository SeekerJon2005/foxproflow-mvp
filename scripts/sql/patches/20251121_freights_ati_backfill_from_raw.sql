-- 20251121_freights_ati_backfill_from_raw.sql
--
-- Цель:
--   • подтянуть исторические ATI-данные из raw.freights_ati_raw
--     в "универсальный" формат public.freights_ati_raw;
--   • не плодить дубли по (src, external_id);
--   • при повторном запуске обновлять payload/parsed_at.
--
-- Предпосылки (ожидаемая схема raw.freights_ati_raw):
--   raw.freights_ati_raw(
--     source        text,   -- источник (ati_html / ati_html_region / и т.п.)
--     source_uid    text,   -- внешний id груза
--     loading_city  text,
--     unloading_city text,
--     cargo         text,
--     body_type     text,
--     loading_date  text,
--     weight        text,
--     volume        text,
--     price         text,
--     parsed_at     timestamptz
--     -- и, возможно, ещё поля (игнорируем)
--   )
--
-- Предпосылки public.freights_ati_raw:
--   public.freights_ati_raw(
--     src          text,
--     external_id  text,
--     payload      jsonb,
--     parsed_at    timestamptz,
--     created_at   timestamptz,
--     ...,
--     UNIQUE (src, external_id)
--   );

BEGIN;

INSERT INTO public.freights_ati_raw (
    src,
    external_id,
    payload,
    parsed_at,
    created_at
)
SELECT
    r.source AS src,
    r.source_uid AS external_id,
    jsonb_build_object(
        'raw', jsonb_build_object(
            'id',           r.source_uid,
            'from_city',    r.loading_city,
            'to_city',      r.unloading_city,
            'cargo',        r.cargo,
            'body',         r.body_type,
            'loading_date', r.loading_date,
            'weight',       r.weight,
            'volume',       r.volume,
            'price',        r.price
        )
    ) AS payload,
    COALESCE(r.parsed_at, NOW()) AS parsed_at,
    NOW() AS created_at
FROM raw.freights_ati_raw AS r
WHERE
    -- не тащим записи без ключей
    r.source     IS NOT NULL
    AND r.source_uid IS NOT NULL
ON CONFLICT (src, external_id) DO UPDATE
SET
    payload   = EXCLUDED.payload,
    parsed_at = EXCLUDED.parsed_at;

COMMIT;

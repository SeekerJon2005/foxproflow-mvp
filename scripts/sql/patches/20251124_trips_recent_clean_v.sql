-- 2025-11-24 — FoxProFlow
-- Временная (но рабочая) витрина trips_recent_clean_v для API /api/trips/recent_clean.
-- Источник: public.trips + meta.autoplan.
-- NDC: только CREATE OR REPLACE VIEW, без ALTER/DROP.

CREATE OR REPLACE VIEW public.trips_recent_clean_v AS
SELECT
    t.id,
    t.status,
    t.created_at,
    t.confirmed_at,
    (t.meta->'autoplan'->>'o')::text AS origin_region,
    (t.meta->'autoplan'->>'d')::text AS dest_region,
    COALESCE((t.meta->'autoplan'->>'price')::numeric, 0) AS price_rub,
    NULL::numeric AS road_km,
    NULL::integer AS drive_sec
FROM public.trips t
WHERE t.created_at >= now() - interval '7 days';

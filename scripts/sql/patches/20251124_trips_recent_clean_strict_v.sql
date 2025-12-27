-- 2025-11-24 — FoxProFlow
-- Строгая витрина рейсов для /api/trips/recent_clean_strict.
-- Источник: public.trips_recent_clean_v.
-- NDC: только CREATE OR REPLACE VIEW.

CREATE OR REPLACE VIEW public.trips_recent_clean_strict_v AS
SELECT *
FROM public.trips_recent_clean_v
WHERE status = 'confirmed';

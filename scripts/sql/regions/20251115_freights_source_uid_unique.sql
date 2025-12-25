-- 2025-11-15 — FoxProFlow
-- Гарантия: один source_uid → один груз в freights.

ALTER TABLE public.freights
ADD CONSTRAINT freights_source_uid_uniq UNIQUE (source_uid);

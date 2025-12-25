-- 20251126_freights_ati_raw_add_created_at.sql
-- Патч выравнивает схему public.freights_ati_raw под regions_data_loader:
-- добавляет колонку created_at, которую использует INSERT
--   INSERT INTO public.freights_ati_raw (src, external_id, payload, parsed_at, created_at) ...

BEGIN;

-- 1. Добавляем колонку created_at, если её ещё нет
ALTER TABLE public.freights_ati_raw
    ADD COLUMN IF NOT EXISTS created_at timestamptz;

-- 2. Ставим DEFAULT для новых строк
ALTER TABLE public.freights_ati_raw
    ALTER COLUMN created_at SET DEFAULT now();

-- 3. Для существующих строк (если вдруг есть) проставляем created_at.
--    Логика:
--      - если уже есть значение created_at — не трогаем;
--      - если нет, но есть parsed_at — используем его;
--      - иначе берём now().
UPDATE public.freights_ati_raw
SET created_at = COALESCE(created_at, parsed_at, now())
WHERE created_at IS NULL;

-- 4. Делаем поле обязательным (код regions_data_loader всегда его заполняет)
ALTER TABLE public.freights_ati_raw
    ALTER COLUMN created_at SET NOT NULL;

COMMIT;

-- 2025-11-21
-- Patch: сделать origin_region/dest_region nullable в od_distance_cache и убрать DEFAULT 'RU-UNK'.
-- Цель: позволить кешу lat/lon хранить множество записей по неизвестным регионам (NULL),
--       не нарушая уникальный индекс origin_region/dest_region/mode.
-- NDC: данные не удаляются; меняем только ограничения и дефолты.

ALTER TABLE public.od_distance_cache
  ALTER COLUMN origin_region DROP NOT NULL,
  ALTER COLUMN dest_region   DROP NOT NULL,
  ALTER COLUMN origin_region DROP DEFAULT,
  ALTER COLUMN dest_region   DROP DEFAULT;

-- Если какие-то строки уже получили 'RU-UNK' как временное значение,
-- переводим их обратно в NULL, чтобы не конфликтовать с уникальным индексом.
UPDATE public.od_distance_cache
SET origin_region = NULL
WHERE origin_region = 'RU-UNK';

UPDATE public.od_distance_cache
SET dest_region = NULL
WHERE dest_region = 'RU-UNK';

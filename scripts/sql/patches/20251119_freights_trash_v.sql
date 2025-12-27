-- scripts/sql/patches/20251119_freights_trash_v.sql
--
-- Назначение:
--   Вьюха для быстрого просмотра "мусорных" фрахтов в public.freights,
--   у которых не определены нормальные регионы погрузки/выгрузки.
--
-- Критерии "треша":
--   - loading_region IS NULL / unloading_region IS NULL
--   - loading_region / unloading_region в ('', 'RU-UNK', 'Н/Д')
--
-- Использование:
--   SELECT * FROM public.freights_trash_v LIMIT 100;
--   -- для диагностики и чистки источника (city_map / нормализация ATI и т.п.)

CREATE OR REPLACE VIEW public.freights_trash_v AS
SELECT
    f.*
FROM public.freights AS f
WHERE
      f.loading_region  IS NULL
   OR f.unloading_region IS NULL
   OR f.loading_region  IN ('', 'RU-UNK', 'Н/Д')
   OR f.unloading_region IN ('', 'RU-UNK', 'Н/Д');

-- 2025-11-15 — FoxProFlow
-- Временный буфер данных из файлов regions_data.

CREATE TABLE IF NOT EXISTS public.freights_fs_import (
    raw_id               text,
    hash                 text,
    region_folder        text,
    loading_city_raw     text,
    unloading_city_raw   text,
    loading_points_raw   text,
    unloading_points_raw text
);

TRUNCATE TABLE public.freights_fs_import;

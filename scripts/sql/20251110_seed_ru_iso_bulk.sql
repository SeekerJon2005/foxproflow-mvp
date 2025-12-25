-- file: scripts/sql/20251110_seed_ru_iso_bulk.sql
-- Идемпотентные вставки (без DO $$), только если записи ещё нет.

INSERT INTO public.region_centroids (code, region, name, lat, lon)
SELECT 'RU-MOW', 'MOSCOW', 'Москва', 55.755800, 37.617300
WHERE NOT EXISTS (SELECT 1 FROM public.region_centroids WHERE UPPER(code)='RU-MOW');

INSERT INTO public.region_centroids (code, region, name, lat, lon)
SELECT 'RU-SPE', 'SAINT PETERSBURG', 'Санкт-Петербург', 59.934300, 30.335100
WHERE NOT EXISTS (SELECT 1 FROM public.region_centroids WHERE UPPER(code)='RU-SPE');

INSERT INTO public.region_centroids (code, region, name, lat, lon)
SELECT 'RU-NIZ', 'NIZHNY NOVGOROD OBLAST', 'Нижегородская область', 56.296500, 43.936100
WHERE NOT EXISTS (SELECT 1 FROM public.region_centroids WHERE UPPER(code)='RU-NIZ');

INSERT INTO public.region_centroids (code, region, name, lat, lon)
SELECT 'RU-VLA', 'VLADIMIR OBLAST', 'Владимирская область', 56.129000, 40.406000
WHERE NOT EXISTS (SELECT 1 FROM public.region_centroids WHERE UPPER(code)='RU-VLA');


-- 20251119_trip_segments_backfill_from_region_centroids.sql
-- FoxProFlow / GEO core
--
-- Назначение:
--   Заполнить src_lat/src_lon и dst_lat/dst_lon в public.trip_segments
--   по таблице public.region_centroids для тех сегментов, где координаты
--   ещё не проставлены.
--
-- Контекст:
--   * region_centroids сидируется патчем 20251118_region_centroids_seed_v2.sql;
--   * этот скрипт предполагается запускать:
--       - после обновления region_centroids,
--       - перед/вместе с routing.enrich.trips, чтобы OSRM имел координаты.
--
-- Свойства:
--   * идемпотентен: обновляет только строки, где src_lat/dst_lat IS NULL;
--   * безопасен для повторного запуска;
--   * не трогает сегменты, у которых координаты уже выставлены (например,
--     если в будущем их проставит более точный геокодер).

-- Источник (origin) — заполняем src_lat/src_lon
UPDATE public.trip_segments s
SET
  src_lat = o.lat,
  src_lon = o.lon
FROM public.region_centroids o
WHERE s.src_lat IS NULL
  AND (o.code = s.origin_region OR lower(o.name) = lower(s.origin_region));

-- Приёмник (destination) — заполняем dst_lat/dst_lon
UPDATE public.trip_segments s
SET
  dst_lat = d.lat,
  dst_lon = d.lon
FROM public.region_centroids d
WHERE s.dst_lat IS NULL
  AND (d.code = s.dest_region OR lower(d.name) = lower(s.dest_region));

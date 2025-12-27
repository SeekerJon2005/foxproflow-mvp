-- Добавляем недостающие поля для дорожных метрик на сегментах
ALTER TABLE IF EXISTS public.trip_segments
  ADD COLUMN IF NOT EXISTS road_km   numeric,
  ADD COLUMN IF NOT EXISTS drive_sec integer,
  ADD COLUMN IF NOT EXISTS polyline  text;

-- Индексы для быстрых выборок/проверок
CREATE INDEX IF NOT EXISTS ix_trip_segments_need_road
  ON public.trip_segments ((road_km IS NULL), (drive_sec IS NULL));

-- По желанию: если есть таблица trips с агрегатом по рейсу — добавь агрегирующие поля туда
-- ALTER TABLE public.trips
--   ADD COLUMN IF NOT EXISTS road_km_total numeric,
--   ADD COLUMN IF NOT EXISTS drive_sec_total integer;

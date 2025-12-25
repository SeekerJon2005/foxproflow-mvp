-- 2025-11-03 — City/Region normalization map v2 (safe/idempotent)
-- Цель: пополнить карту соответствий, чтобы привести кириллицу из ваших топов к ISO.

BEGIN;

CREATE TABLE IF NOT EXISTS public.city_to_region_map(
  name        text PRIMARY KEY,
  region_code text NOT NULL
);

-- Базовые столицы
INSERT INTO public.city_to_region_map(name, region_code) VALUES
  ('МОСКВА','RU-MOW'),
  ('САНКТ-ПЕТЕРБУРГ','RU-SPE'),
  ('СПБ','RU-SPE'),
  ('С-ПЕТЕРБУРГ','RU-SPE')
ON CONFLICT DO NOTHING;

-- Из ваших отчётов (ТОПы)
INSERT INTO public.city_to_region_map(name, region_code) VALUES
  ('ЗАБАЙКАЛЬСКИЙ КРАЙ','RU-ZAB'), ('ЧИТА','RU-ZAB'),
  ('ВЛАДИМИРСКАЯ ОБЛАСТЬ','RU-VLA'), ('ВЛАДИМИР','RU-VLA'),
  ('АЛТАЙСКИЙ КРАЙ','RU-ALT'), ('БАРНАУЛ','RU-ALT'),
  ('АМУРСКАЯ ОБЛАСТЬ','RU-AMU'), ('БЛАГОВЕЩЕНСК','RU-AMU'),
  ('БЕЛГОРОДСКАЯ ОБЛАСТЬ','RU-BEL'), ('БЕЛГОРОД','RU-BEL'),
  ('БРЯНСКАЯ ОБЛАСТЬ','RU-BRY'), ('БРЯНСК','RU-BRY'),
  ('ВОРОНЕЖСКАЯ ОБЛАСТЬ','RU-VOR'), ('ВОРОНЕЖ','RU-VOR'),
  ('ВОЛОГОДСКАЯ ОБЛАСТЬ','RU-VLG'), ('ВОЛОГДА','RU-VLG'),
  ('АРХАНГЕЛЬСК','RU-ARK'),
  ('ИВАНОВСКАЯ ОБЛАСТЬ','RU-IVA'), ('ИВАНОВО','RU-IVA')
ON CONFLICT DO NOTHING;

-- Дополнение на будущее (частые регионы)
INSERT INTO public.city_to_region_map(name, region_code) VALUES
  ('ЛЕНИНГРАДСКАЯ ОБЛАСТЬ','RU-LEN'),
  ('КРАСНОДАРСКИЙ КРАЙ','RU-KDA'),
  ('КРАСНОЯРСКИЙ КРАЙ','RU-KYA'),
  ('НОВОСИБИРСКАЯ ОБЛАСТЬ','RU-NVS'),
  ('ТУЛЬСКАЯ ОБЛАСТЬ','RU-TUL'),
  ('ЯРОСЛАВСКАЯ ОБЛАСТЬ','RU-YAR')
ON CONFLICT DO NOTHING;

COMMIT;

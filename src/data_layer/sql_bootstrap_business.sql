
-- =============================================
-- FoxProFlow — бизнесовый «бутстрап» (DDL + MV)
-- =============================================

-- 0) Безопасно удаляем конфликтующее VIEW, если оно ещё есть
DROP VIEW IF EXISTS freights_enriched CASCADE;

-- 1) Сырые таблицы (создаём осторожно, если отсутствуют)
CREATE TABLE IF NOT EXISTS freights (
  id                text PRIMARY KEY,
  hash              varchar(32),
  loading_city      text,
  unloading_city    text,
  distance          real,
  cargo             text,
  weight            real,
  volume            real,
  body_type         text,
  loading_date      timestamptz,              -- важно: дата/время погрузки в нормальном типе
  revenue_rub       numeric(14,2),
  profit_per_km     numeric(10,2),
  loading_lat       real,
  loading_lon       real,
  unloading_lat     real,
  unloading_lon     real,
  loading_region    text,
  unloading_region  text,
  parsed_at         timestamptz default now(),
  session_id        integer,
  source            varchar(50)
);

CREATE TABLE IF NOT EXISTS macro_data (
  id             serial PRIMARY KEY,
  date           date NOT NULL,               -- день, к которому относится замер
  usd_rate       numeric(10,4),
  eur_rate       numeric(10,4),
  fuel_price_avg numeric(10,2),
  source         text,
  updated_at     timestamptz default now()
);
CREATE UNIQUE INDEX IF NOT EXISTS macro_data_date_uq ON macro_data(date);

CREATE TABLE IF NOT EXISTS transport_demand (
  id               serial PRIMARY KEY,
  region           text NOT NULL,
  trucks_available integer,
  requests         integer,
  date             date NOT NULL,
  parsed_at        timestamptz default now()
);
CREATE UNIQUE INDEX IF NOT EXISTS transport_demand_region_date_uq ON transport_demand(region, date);

-- 2) MATERIALIZED VIEW для быстрого чтения API
DROP MATERIALIZED VIEW IF EXISTS freights_enriched_mv;
CREATE MATERIALIZED VIEW freights_enriched_mv AS
SELECT
  f.id,
  f.hash,
  f.loading_city,
  f.unloading_city,
  f.distance,
  f.cargo,
  f.weight,
  f.volume,
  f.body_type,
  f.loading_date,
  f.revenue_rub,
  f.profit_per_km,
  f.loading_lat,
  f.loading_lon,
  f.unloading_lat,
  f.unloading_lon,
  f.loading_region,
  f.unloading_region,
  f.parsed_at,
  f.session_id,
  f.source,
  md.usd_rate,
  md.eur_rate,
  md.fuel_price_avg,
  td_loading.trucks_available AS loading_region_trucks,
  td_loading.requests         AS loading_region_requests,
  td_unloading.trucks_available AS unloading_region_trucks,
  td_unloading.requests         AS unloading_region_requests
FROM freights f
LEFT JOIN LATERAL (
  SELECT m.usd_rate, m.eur_rate, m.fuel_price_avg
  FROM macro_data m
  WHERE m.date <= (f.loading_date AT TIME ZONE 'UTC')::date
  ORDER BY m.date DESC
  LIMIT 1
) md ON TRUE
LEFT JOIN LATERAL (
  SELECT t.trucks_available, t.requests
  FROM transport_demand t
  WHERE t.region = f.loading_region
    AND t.date <= (f.loading_date AT TIME ZONE 'UTC')::date
  ORDER BY t.date DESC
  LIMIT 1
) td_loading ON TRUE
LEFT JOIN LATERAL (
  SELECT t.trucks_available, t.requests
  FROM transport_demand t
  WHERE t.region = f.unloading_region
    AND t.date <= (f.loading_date AT TIME ZONE 'UTC')::date
  ORDER BY t.date DESC
  LIMIT 1
) td_unloading ON TRUE;

-- Индексы на MV под фильтры/сортировки ручки /freights
CREATE INDEX IF NOT EXISTS fe_mv_loading_city_idx    ON freights_enriched_mv(loading_city);
CREATE INDEX IF NOT EXISTS fe_mv_unloading_city_idx  ON freights_enriched_mv(unloading_city);
CREATE INDEX IF NOT EXISTS fe_mv_loading_date_idx    ON freights_enriched_mv(loading_date);
CREATE INDEX IF NOT EXISTS fe_mv_parsed_at_desc_idx  ON freights_enriched_mv(loading_date DESC, parsed_at DESC);

-- 3) Минимальные демо-данные (по желанию): макро и спрос
INSERT INTO macro_data(date, usd_rate, eur_rate, fuel_price_avg, source)
VALUES
  (CURRENT_DATE - INTERVAL '1 day', 90.00, 95.00, 58.50, 'seed'),
  (CURRENT_DATE,                    90.20, 95.10, 58.60, 'seed')
ON CONFLICT (date) DO NOTHING;

INSERT INTO transport_demand(region, trucks_available, requests, date, parsed_at)
VALUES
  ('Москва', 120, 340, CURRENT_DATE, now()),
  ('СПб',     95, 280, CURRENT_DATE, now())
ON CONFLICT (region, date) DO NOTHING;

-- Примечание: таблица freights НЕ наполняется здесь. Её наполняет ваш ETL/парсер.
-- После появления данных в freights — обновляйте MV:
--   REFRESH MATERIALIZED VIEW CONCURRENTLY freights_enriched_mv;


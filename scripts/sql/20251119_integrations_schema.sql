-- 2025-11-19 FoxProFlow — интеграции, ingest, нормализация (NDC)
BEGIN;

CREATE SCHEMA IF NOT EXISTS integrations;
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS market;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Реестр источников и их аккаунтов
CREATE TABLE IF NOT EXISTS integrations.sources (
  id            bigserial PRIMARY KEY,
  code          text UNIQUE NOT NULL,    -- "ati", "torgtrans", "tmsru", "monopoly"
  kind          text NOT NULL CHECK (kind IN ('api','web','email')),
  active        boolean NOT NULL DEFAULT true,
  rate_qps      numeric(8,3) DEFAULT 1.0,
  rate_burst    integer      DEFAULT 5,
  meta          jsonb        DEFAULT '{}'::jsonb,
  created_at    timestamptz  NOT NULL DEFAULT now(),
  updated_at    timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS integrations.accounts (
  id            bigserial PRIMARY KEY,
  source_id     bigint NOT NULL REFERENCES integrations.sources(id) ON DELETE CASCADE,
  name          text   NOT NULL,
  secrets       jsonb  NOT NULL DEFAULT '{}'::jsonb,
  state         jsonb  NOT NULL DEFAULT '{}'::jsonb,
  last_ok_at    timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, name)
);

-- Сырые события ingest
CREATE TABLE IF NOT EXISTS ingest.raw_events (
  id            bigserial PRIMARY KEY,
  source_id     bigint NOT NULL REFERENCES integrations.sources(id) ON DELETE RESTRICT,
  account_id    bigint REFERENCES integrations.accounts(id) ON DELETE SET NULL,
  kind          text   NOT NULL,              -- 'api'|'web'|'email'
  external_id   text,
  payload       jsonb NOT NULL,
  pulled_at     timestamptz NOT NULL DEFAULT now(),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS raw_events_source_time_idx ON ingest.raw_events(source_id, pulled_at DESC);
CREATE INDEX IF NOT EXISTS raw_events_ext_idx        ON ingest.raw_events(external_id);

-- Курсоры поллинга
CREATE TABLE IF NOT EXISTS ingest.cursors (
  id            bigserial PRIMARY KEY,
  source_id     bigint NOT NULL REFERENCES integrations.sources(id) ON DELETE CASCADE,
  account_id    bigint REFERENCES integrations.accounts(id) ON DELETE CASCADE,
  key           text   NOT NULL,
  value         jsonb  NOT NULL,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, account_id, key)
);

-- «Плоское сырьё» по фрахтам
CREATE TABLE IF NOT EXISTS market.freights_raw (
  id            bigserial PRIMARY KEY,
  source        text    NOT NULL,
  external_id   text    NOT NULL,
  origin_text   text,
  dest_text     text,
  price_rub     numeric(14,2),
  payload       jsonb   NOT NULL,
  parsed_at     timestamptz NOT NULL DEFAULT now(),
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS freights_raw_parsed_idx ON market.freights_raw(parsed_at DESC);

-- Нормализованный слой
CREATE TABLE IF NOT EXISTS market.freights_norm (
  id               bigserial PRIMARY KEY,
  source           text    NOT NULL,
  source_uid       text    NOT NULL,
  origin_text      text    NOT NULL,
  dest_text        text    NOT NULL,
  loading_region   text,
  unloading_region text,
  origin_lat       double precision,
  origin_lon       double precision,
  dest_lat         double precision,
  dest_lon         double precision,
  loading_date     timestamptz,
  revenue_rub      numeric(14,2),
  geo_ok           boolean NOT NULL DEFAULT false,
  status           text    NOT NULL DEFAULT 'needs_geo',
  meta             jsonb   NOT NULL DEFAULT '{}'::jsonb,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source, source_uid)
);

-- Хелпер: строка похожа на код региона (RU-MOW и пр.)
CREATE OR REPLACE FUNCTION market.is_region_code(x text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT x ~ '^[A-Z]{2}-[A-Z0-9]{2,3}$'
         OR x ~ '^RU-[A-Z0-9]{2,3}$';
$$;

-- Хелпер: O/D «слишком широкий» (оба — регионы, без координат)
CREATE OR REPLACE FUNCTION market.is_too_wide_od(
  o    text,
  d    text,
  olat double precision,
  olon double precision,
  dlat double precision,
  dlon double precision
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT (market.is_region_code(o) AND market.is_region_code(d))
         AND (olat IS NULL OR olon IS NULL OR dlat IS NULL OR dlon IS NULL);
$$;

-- CHECK: статус ready только если есть координаты и O/D не «чисто регионы»
ALTER TABLE market.freights_norm
  ADD CONSTRAINT freights_norm_ready_ck CHECK (
    (status <> 'ready')
    OR (
      geo_ok = true
      AND origin_lat IS NOT NULL AND origin_lon IS NOT NULL
      AND dest_lat  IS NOT NULL AND dest_lon  IS NOT NULL
      AND NOT market.is_too_wide_od(origin_text, dest_text, origin_lat, origin_lon, dest_lat, dest_lon)
    )
  );

-- Триггер-гвард: авторасстановка geo_ok/status
CREATE OR REPLACE FUNCTION market.fn_freights_norm_status_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.geo_ok := (
    NEW.origin_lat IS NOT NULL AND NEW.origin_lon IS NOT NULL
    AND NEW.dest_lat IS NOT NULL AND NEW.dest_lon IS NOT NULL
  );

  IF market.is_too_wide_od(
       NEW.origin_text,
       NEW.dest_text,
       NEW.origin_lat,
       NEW.origin_lon,
       NEW.dest_lat,
       NEW.dest_lon
     )
  THEN
    NEW.status := 'needs_geo';
  ELSIF NEW.geo_ok THEN
    NEW.status := 'ready';
  ELSE
    NEW.status := COALESCE(NULLIF(NEW.status, ''), 'needs_geo');
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_freights_norm_guard_biur ON market.freights_norm;

CREATE TRIGGER trg_freights_norm_guard_biur
  BEFORE INSERT OR UPDATE ON market.freights_norm
  FOR EACH ROW
  EXECUTE FUNCTION market.fn_freights_norm_status_guard();

-- Витрина: что ещё требует гео
CREATE OR REPLACE VIEW market.freights_needs_geo_v AS
SELECT *
FROM market.freights_norm
WHERE status = 'needs_geo'
ORDER BY created_at DESC;

COMMIT;

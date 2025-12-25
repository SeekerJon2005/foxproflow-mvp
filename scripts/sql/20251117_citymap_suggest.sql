BEGIN;

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.citymap_suggest (
  id              bigserial PRIMARY KEY,
  place_key       text        NOT NULL,
  region_guess    text        NOT NULL,
  samples         integer     NOT NULL,
  region_variants integer     NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  last_seen_at    timestamptz NOT NULL DEFAULT now(),
  used            boolean     NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX IF NOT EXISTS citymap_suggest_place_region_uq
  ON ops.citymap_suggest (place_key, region_guess);

-- Индекс для выборки "новых/неиспользованных" предложений
CREATE INDEX IF NOT EXISTS citymap_suggest_unused_idx
  ON ops.citymap_suggest (used, created_at DESC);

COMMENT ON SCHEMA ops IS
  'Вспомогательные/операционные структуры FoxProFlow (агенты, мониторинг, предложения).';

COMMENT ON TABLE ops.citymap_suggest IS
  'Предложения по маппингу городских ключей (place_key) к региону (region_guess) от агента agents.citymap.suggest.';

COMMENT ON COLUMN ops.citymap_suggest.place_key       IS 'Нормализованный ключ города из freights_from_ati_* (loading_place_key/unloading_place_key).';
COMMENT ON COLUMN ops.citymap_suggest.region_guess    IS 'Предлагаемый ISO-код региона (например RU-MOW).';
COMMENT ON COLUMN ops.citymap_suggest.samples         IS 'Число строк freights, на которых основано предложение.';
COMMENT ON COLUMN ops.citymap_suggest.region_variants IS 'Сколько разных регионов встречалось для данного place_key (1 = чистый сигнал).';
COMMENT ON COLUMN ops.citymap_suggest.created_at      IS 'Когда предложение впервые зафиксировано.';
COMMENT ON COLUMN ops.citymap_suggest.last_seen_at    IS 'Когда place_key/region_guess в последний раз был встречен источником.';
COMMENT ON COLUMN ops.citymap_suggest.used            IS 'Флаг, что предложение уже отработано (учтено при обновлении city_map).';

COMMIT;

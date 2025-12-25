-- file: scripts/sql/patches/20251125_market_brain_schema.sql
-- FoxProFlow — Market Brain L0 schema (demand_forecast + virtual_freights)
-- NDC: только создание схемы и таблиц + комментарии/ограничения.

CREATE SCHEMA IF NOT EXISTS market;

-- Прогноз спроса по коридорам (OD + день)
CREATE TABLE IF NOT EXISTS market.demand_forecast (
    id              bigserial PRIMARY KEY,
    day             date        NOT NULL,          -- loading_date::date
    origin_region   text        NOT NULL,          -- loading_region / corridor.origin_region
    dest_region     text        NOT NULL,          -- unloading_region / corridor.dest_region
    n               bigint      NOT NULL,          -- количество наблюдений
    rpm_p50         numeric(10,2),                 -- медиана RPM
    rpm_p25         numeric(10,2),                 -- нижний квартиль RPM
    rpm_p75         numeric(10,2),                 -- верхний квартиль RPM
    generated_by    text        NOT NULL
                    DEFAULT 'MarketBrain.ati_v1',
    created_at      timestamptz NOT NULL
                    DEFAULT now(),
    meta            jsonb       NOT NULL
                    DEFAULT '{}'::jsonb,
    CONSTRAINT demand_forecast_n_nonnegative
        CHECK (n >= 0),
    CONSTRAINT demand_forecast_rpm_nonnegative
        CHECK (
            (rpm_p25 IS NULL OR rpm_p25 >= 0)
            AND (rpm_p50 IS NULL OR rpm_p50 >= 0)
            AND (rpm_p75 IS NULL OR rpm_p75 >= 0)
        )
);

CREATE INDEX IF NOT EXISTS ix_market_demand_forecast_day_od
    ON market.demand_forecast (day, origin_region, dest_region);

-- Виртуальные фрахты (заявки, которых нет, но рынок их "ожидает")
CREATE TABLE IF NOT EXISTS market.virtual_freights (
    id              bigserial PRIMARY KEY,
    day             date        NOT NULL,          -- целевой день загрузки
    origin_region   text        NOT NULL,          -- регион погрузки
    dest_region     text        NOT NULL,          -- регион выгрузки
    rpm_expected    numeric(10,2),                 -- ожидаемый RPM по коридору
    probability     numeric(5,4) NOT NULL,         -- 0..1 — вероятность появления
    generated_by    text        NOT NULL,          -- 'MarketBrain.v1', 'MarketBrain.test' и т.п.
    created_at      timestamptz NOT NULL
                    DEFAULT now(),
    meta            jsonb       NOT NULL
                    DEFAULT '{}'::jsonb,
    CONSTRAINT virtual_freights_probability_valid
        CHECK (probability >= 0 AND probability <= 1),
    CONSTRAINT virtual_freights_rpm_nonnegative
        CHECK (rpm_expected IS NULL OR rpm_expected >= 0)
);

CREATE INDEX IF NOT EXISTS ix_market_virtual_freights_day_od
    ON market.virtual_freights (day, origin_region, dest_region);

-- Комментарии для удобства в psql и графических клиентах

COMMENT ON SCHEMA market IS
    'Market Brain: прогноз спроса и виртуальные фрахты';

COMMENT ON TABLE market.demand_forecast IS
    'Агрегированный спрос по коридорам (day + origin_region + dest_region) с RPM-квантилями';

COMMENT ON COLUMN market.demand_forecast.day IS
    'Дата загрузки (loading_date::date)';

COMMENT ON COLUMN market.demand_forecast.origin_region IS
    'Нормализованный регион погрузки (origin_region)';

COMMENT ON COLUMN market.demand_forecast.dest_region IS
    'Нормализованный регион выгрузки (dest_region)';

COMMENT ON COLUMN market.demand_forecast.n IS
    'Число наблюдений по коридору за день';

COMMENT ON COLUMN market.demand_forecast.rpm_p25 IS
    '25-й перцентиль RPM по коридору';

COMMENT ON COLUMN market.demand_forecast.rpm_p50 IS
    '50-й перцентиль (медиана) RPM по коридору';

COMMENT ON COLUMN market.demand_forecast.rpm_p75 IS
    '75-й перцентиль RPM по коридору';

COMMENT ON COLUMN market.demand_forecast.generated_by IS
    'Источник/версия пайплайна Market Brain, который сгенерировал строку';

COMMENT ON COLUMN market.demand_forecast.meta IS
    'Произвольный JSONB с дополнительными метаданными (размер окна и т.п.)';

COMMENT ON TABLE market.virtual_freights IS
    'Виртуальные фрахты: заявки, которых ещё нет, но рынок их ожидает (по данным Market Brain)';

COMMENT ON COLUMN market.virtual_freights.day IS
    'Дата, на которую сгенерирован виртуальный фрахт';

COMMENT ON COLUMN market.virtual_freights.origin_region IS
    'Регион погрузки виртуального фрахта';

COMMENT ON COLUMN market.virtual_freights.dest_region IS
    'Регион выгрузки виртуального фрахта';

COMMENT ON COLUMN market.virtual_freights.rpm_expected IS
    'Ожидаемый RPM по коридору для виртуального фрахта';

COMMENT ON COLUMN market.virtual_freights.probability IS
    'Вероятность появления реального фрахта в этом коридоре (0..1)';

COMMENT ON COLUMN market.virtual_freights.generated_by IS
    'Источник/версия пайплайна Market Brain, который создал виртуальный фрахт';

COMMENT ON COLUMN market.virtual_freights.meta IS
    'Дополнительные метаданные (причины генерации, флаги и т.п.)';

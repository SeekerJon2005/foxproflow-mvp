-- scripts/sql/patches/20251120_analytics_dynrpm_config.sql
-- NDC-патч: создаёт таблицу конфигурации DynRPM для последующего использования агентами.
-- Не трогает существующие объекты.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.dynrpm_config
(
    id               bigserial PRIMARY KEY,

    -- Код бакета, по которому будем ссылаться из FlowLang/агентов
    -- (например, 'short', 'medium', 'long')
    bucket_code      text        NOT NULL,

    -- Человеко-читаемое имя бакета
    bucket_name      text,

    -- Диапазон дистанций в км (интерпретация договорная;
    -- можно использовать 0–300, 300–800, 800+ и т.п.)
    distance_km_min  numeric,
    distance_km_max  numeric,

    -- Квантили RPM, рассчитанные по данным ATI (будет заполнять агент dynrpm)
    rpm_p25          numeric,
    rpm_p50          numeric,
    rpm_p75          numeric,

    -- Фактически используемый floor RPM для этого бакета
    rpm_floor        numeric,

    -- Временная метка последнего обновления записи
    updated_at       timestamptz NOT NULL DEFAULT now(),

    -- Уникальность по bucket_code, чтобы не плодить дублей
    CONSTRAINT dynrpm_config_bucket_uq UNIQUE (bucket_code),

    -- Базовая защита от мусора в данных (NULL допустим, но отрицательные значения — нет)
    CONSTRAINT dynrpm_dist_min_nonneg_chk
        CHECK (distance_km_min IS NULL OR distance_km_min >= 0),
    CONSTRAINT dynrpm_dist_max_nonneg_chk
        CHECK (distance_km_max IS NULL OR distance_km_max >= 0),
    CONSTRAINT dynrpm_rpm_p25_nonneg_chk
        CHECK (rpm_p25 IS NULL OR rpm_p25 >= 0),
    CONSTRAINT dynrpm_rpm_p50_nonneg_chk
        CHECK (rpm_p50 IS NULL OR rpm_p50 >= 0),
    CONSTRAINT dynrpm_rpm_p75_nonneg_chk
        CHECK (rpm_p75 IS NULL OR rpm_p75 >= 0),
    CONSTRAINT dynrpm_rpm_floor_nonneg_chk
        CHECK (rpm_floor IS NULL OR rpm_floor >= 0)
);

COMMENT ON TABLE analytics.dynrpm_config IS
    'Конфигурация DynRPM по бакетам расстояния: квантили RPM и floor-значения для планировщика';

COMMENT ON COLUMN analytics.dynrpm_config.bucket_code IS
    'Код бакета (например, short/medium/long или custom)';
COMMENT ON COLUMN analytics.dynrpm_config.distance_km_min IS
    'Нижняя граница дистанции (км), может быть NULL для открытого интервала';
COMMENT ON COLUMN analytics.dynrpm_config.distance_km_max IS
    'Верхняя граница дистанции (км), может быть NULL для открытого интервала';
COMMENT ON COLUMN analytics.dynrpm_config.rpm_floor IS
    'Фактический floor RPM, который будет использоваться в планах (может отличаться от статистических квантилей)';

-- ---------------------------------------------------------------------------
-- Первоначальные бакеты по умолчанию (short / medium / long).
-- Это только начальная разметка; значения RPM будут выставлять агенты.
-- ON CONFLICT гарантирует, что повторный прогон патча не создаст дубликаты.
-- ---------------------------------------------------------------------------

INSERT INTO analytics.dynrpm_config (bucket_code, bucket_name, distance_km_min, distance_km_max)
VALUES
    ('short',  'Short distance (0–300 km)',   0,   300),
    ('medium', 'Medium distance (300–800 km)', 300, 800),
    ('long',   'Long distance (800+ km)',     800, NULL)
ON CONFLICT (bucket_code) DO NOTHING;

-- 20251125_driver_alerts.sql
-- FoxProFlow — алерты по движению водителей (off-route, ETA и т.п.).
-- NDC: только CREATE SCHEMA IF NOT EXISTS, CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.driver_alerts (
    id         bigserial PRIMARY KEY,
    ts         timestamptz NOT NULL DEFAULT now(),
    trip_id    uuid        NOT NULL,
    driver_id  uuid,
    alert_type text        NOT NULL,  -- off_route, eta_delay, speed, ...
    level      text        NOT NULL,  -- info, warn, critical
    message    text,
    details    jsonb       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE ops.driver_alerts IS
    'События/алерты по поведению водителя (off-route, задержки по ETA и др.).';

COMMENT ON COLUMN ops.driver_alerts.id IS
    'Технический идентификатор алерта (bigserial).';

COMMENT ON COLUMN ops.driver_alerts.ts IS
    'Время возникновения/фиксации алерта (UTC).';

COMMENT ON COLUMN ops.driver_alerts.trip_id IS
    'Рейс, к которому относится алерт.';

COMMENT ON COLUMN ops.driver_alerts.driver_id IS
    'Водитель, к которому относится алерт.';

COMMENT ON COLUMN ops.driver_alerts.alert_type IS
    'Тип алерта (off_route, eta_delay, speed_limit и т.п.).';

COMMENT ON COLUMN ops.driver_alerts.level IS
    'Уровень важности (info, warn, critical).';

COMMENT ON COLUMN ops.driver_alerts.message IS
    'Краткое человекочитаемое описание алерта.';

COMMENT ON COLUMN ops.driver_alerts.details IS
    'Структурированные параметры алерта (расстояния, detour_factor, ETA и т.п.).';

CREATE INDEX IF NOT EXISTS idx_driver_alerts_trip_ts
    ON ops.driver_alerts (trip_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_driver_alerts_driver_ts
    ON ops.driver_alerts (driver_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_driver_alerts_type_ts
    ON ops.driver_alerts (alert_type, ts DESC);

-- Индекс под выборки последних алертов без фильтра
CREATE INDEX IF NOT EXISTS idx_driver_alerts_ts_desc
    ON ops.driver_alerts (ts DESC);

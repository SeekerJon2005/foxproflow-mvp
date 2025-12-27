-- FoxProFlow • FixPack • ops.driver_alerts base table for driver off-route alerts
-- file: scripts/sql/fixpacks/20251219_ops_driver_alerts_apply.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Notes:
-- - Idempotent (safe повторный запуск)
-- - Создаёт ops.driver_alerts, индексы под "recent alert" и "active alerts"
-- - Trip/driver IDs храним как text (универсально; защищает от uuid/text/int mismatch)

BEGIN;

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.driver_alerts (
    id               BIGSERIAL PRIMARY KEY,
    ts               TIMESTAMPTZ NOT NULL DEFAULT now(),

    trip_id           TEXT NOT NULL,
    driver_id         TEXT,

    alert_type        TEXT NOT NULL,
    level             TEXT NOT NULL,
    message           TEXT,
    details           JSONB NOT NULL DEFAULT '{}'::jsonb,

    resolved_at       TIMESTAMPTZ,
    resolved_by       TEXT,
    resolved_comment  TEXT
);

-- Индексы под частые запросы (recent alert / active alert)
CREATE INDEX IF NOT EXISTS ops_driver_alerts_trip_type_ts_idx
    ON ops.driver_alerts (trip_id, alert_type, ts DESC);

CREATE INDEX IF NOT EXISTS ops_driver_alerts_open_trip_type_ts_idx
    ON ops.driver_alerts (trip_id, alert_type, ts DESC)
    WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS ops_driver_alerts_ts_idx
    ON ops.driver_alerts (ts DESC);

COMMENT ON TABLE ops.driver_alerts IS 'Telemetry-derived driver alerts (off_route, etc). Created by FoxProFlow FixPack 20251219.';
COMMENT ON COLUMN ops.driver_alerts.trip_id IS 'Trip id (stored as text for compatibility with uuid/bigint/string sources).';
COMMENT ON COLUMN ops.driver_alerts.driver_id IS 'Driver id (stored as text for compatibility).';

COMMIT;

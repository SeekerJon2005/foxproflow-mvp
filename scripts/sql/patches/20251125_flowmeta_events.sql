-- 20251125_flowmeta_events.sql
-- FoxProFlow — события FlowMeta/FlowSec в общей схеме ops.
-- NDC: только CREATE TABLE/INDEX IF NOT EXISTS, никаких ALTER/DROP.

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.flowmeta_events (
    id           bigserial PRIMARY KEY,
    ts           timestamptz NOT NULL DEFAULT now(),
    source       text        NOT NULL DEFAULT 'flowmeta.validate',
    world_name   text        NOT NULL,
    ok           boolean     NOT NULL,
    n_violations integer     NOT NULL,
    severity_max text        NOT NULL,      -- 'info' | 'warning' | 'error'
    payload      jsonb       NOT NULL,      -- полный результат validate_world(...)
    meta         jsonb       NOT NULL DEFAULT '{}'::jsonb
);

-- Основная сортировка — по времени (последние события)
CREATE INDEX IF NOT EXISTS ix_flowmeta_events_ts
    ON ops.flowmeta_events (ts DESC);

-- Быстрый выбор "всё ок / есть проблемы"
CREATE INDEX IF NOT EXISTS ix_flowmeta_events_ok
    ON ops.flowmeta_events (ok);

-- Фильтрация по максимальной серьёзности
CREATE INDEX IF NOT EXISTS ix_flowmeta_events_severity
    ON ops.flowmeta_events (severity_max);

-- Быстрый просмотр истории по конкретному миру (foxproflow / другие)
CREATE INDEX IF NOT EXISTS ix_flowmeta_events_world_ts
    ON ops.flowmeta_events (world_name, ts DESC);

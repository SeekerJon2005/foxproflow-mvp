-- 20251124_ops_event_log.sql
-- Базовые таблицы событий для Observability 2.0

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.event_log (
    id             bigserial PRIMARY KEY,
    ts             timestamptz NOT NULL DEFAULT now(),
    source         text        NOT NULL,              -- откуда событие: 'autoplan','etl','geo','agent','api','flowsec',...
    event_type     text        NOT NULL,              -- тип: 'start','done','error','noop','anomaly','decision',...
    severity       text        NOT NULL DEFAULT 'info', -- уровень: 'info','warn','error','critical'
    correlation_id text,                              -- идентификатор цепочки / запроса / task_id
    tenant_id      text,                              -- будущий multi-tenant
    payload        jsonb                               -- произвольные данные события
);

CREATE INDEX IF NOT EXISTS event_log_ts_idx
    ON ops.event_log (ts);

CREATE INDEX IF NOT EXISTS event_log_source_ts_idx
    ON ops.event_log (source, ts);

CREATE INDEX IF NOT EXISTS event_log_correlation_idx
    ON ops.event_log (correlation_id);

CREATE TABLE IF NOT EXISTS ops.event_links (
    parent_id bigint NOT NULL REFERENCES ops.event_log(id) ON DELETE CASCADE,
    child_id  bigint NOT NULL REFERENCES ops.event_log(id) ON DELETE CASCADE,
    relation  text   NOT NULL DEFAULT 'caused',
    PRIMARY KEY (parent_id, child_id, relation)
);

CREATE INDEX IF NOT EXISTS event_links_parent_idx
    ON ops.event_links (parent_id);

CREATE INDEX IF NOT EXISTS event_links_child_idx
    ON ops.event_links (child_id);

-- 20251124_ops_event_views.sql
-- Базовые вьюшки для событий Observability 2.0

CREATE SCHEMA IF NOT EXISTS analytics;

-- 1. Последние события за 24 часа (для любых источников)
CREATE OR REPLACE VIEW analytics.events_recent_v AS
SELECT
    id,
    ts,
    source,
    event_type,
    severity,
    correlation_id,
    tenant_id,
    payload
FROM ops.event_log
WHERE ts >= now() - interval '24 hours'
ORDER BY ts DESC;

-- 2. Последние ошибки / критичные события за 24 часа
CREATE OR REPLACE VIEW analytics.events_errors_recent_v AS
SELECT
    id,
    ts,
    source,
    event_type,
    severity,
    correlation_id,
    tenant_id,
    payload
FROM ops.event_log
WHERE ts >= now() - interval '24 hours'
  AND severity IN ('error', 'critical')
ORDER BY ts DESC;

-- 3. Суточная статистика по источникам/типам событий
CREATE OR REPLACE VIEW analytics.events_by_source_daily_v AS
SELECT
    date_trunc('day', ts)::date   AS day,
    source,
    event_type,
    severity,
    count(*)                      AS cnt
FROM ops.event_log
GROUP BY 1, 2, 3, 4
ORDER BY day DESC, source, event_type, severity;

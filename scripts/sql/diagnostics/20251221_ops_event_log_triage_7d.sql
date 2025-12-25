-- FoxProFlow • OPS/DEV • Triage: ops.event_log errors (last 7d)
-- file: scripts/sql/diagnostics/20251221_ops_event_log_triage_7d.sql
-- Created by: Архитектор Яцков Евгений Анатольевич
-- Purpose:
--  - Top groupings by source/event_type/(action)
--  - Top normalized reasons + 5 payload samples per reason
--  - первичная классификация expected vs actionable
--
-- Notes:
--  - action извлекается из payload (action/op/route/path/request.*).
--  - reason_sig нормализует UUID и числа -> чтобы группировать “одну и ту же” ошибку.
--  - Скрипт читает только последние :days дней.

\set ON_ERROR_STOP on
\pset pager off

\set days 7
\set top_groups 30
\set top_reasons 10
\set samples_per_reason 5
\set payload_chars 1200
\set msg_chars 220
\set reason_chars 260

\echo '================================================================='
\echo 'FoxProFlow • OPS/DEV report: ops.event_log error triage'
\echo 'Period: last :'days' days'
\echo 'Generated at:'
SELECT now() AS generated_at,
       now() - make_interval(days => :days::int) AS from_ts;

-- ================
-- Build working set (TEMP)
-- ================
DROP TABLE IF EXISTS temp_ops_event_err;

CREATE TEMP TABLE temp_ops_event_err AS
WITH raw AS (
  SELECT
    id,
    COALESCE(ts, created_at) AS event_ts,
    NULLIF(source,'')       AS source,
    NULLIF(event_type,'')   AS event_type,
    NULLIF(type,'')         AS legacy_type,
    LOWER(NULLIF(severity,'')) AS severity,
    ok,
    correlation_id,
    actor,
    message,
    payload
  FROM ops.event_log
  WHERE COALESCE(ts, created_at) >= now() - make_interval(days => :days::int)
),
err AS (
  SELECT
    *,
    (
      ok IS FALSE
      OR LOWER(COALESCE(severity,'')) IN ('error','critical','fatal')
      OR LOWER(COALESCE(event_type, legacy_type,'')) LIKE '%error%'
      OR LOWER(COALESCE(message,'')) LIKE '%exception%'
      OR LOWER(COALESCE(message,'')) LIKE '%traceback%'
    ) AS is_error
  FROM raw
),
base AS (
  SELECT
    id,
    event_ts,
    COALESCE(source, 'unknown') AS source,
    event_type,
    legacy_type,
    LOWER(COALESCE(severity,'')) AS severity,
    ok,
    correlation_id,
    actor,
    message,
    payload,

    -- action extraction (best effort)
    NULLIF(
      COALESCE(
        NULLIF(payload->>'action',''),
        NULLIF(payload->>'op',''),
        NULLIF(payload->>'operation',''),
        NULLIF(payload->>'method',''),
        NULLIF(payload->>'endpoint',''),
        NULLIF(payload->>'route',''),
        NULLIF(payload->>'path',''),
        NULLIF(payload#>>'{meta,action}',''),
        NULLIF(payload#>>'{meta,op}',''),
        NULLIF(payload#>>'{request,endpoint}',''),
        NULLIF(concat_ws(' ', NULLIF(payload#>>'{request,method}',''), NULLIF(payload#>>'{request,path}','')),'')
      ),
      ''
    ) AS action,

    -- common codes (if present)
    NULLIF(
      COALESCE(
        NULLIF(payload->>'sqlstate',''),
        NULLIF(payload->>'pgcode',''),
        NULLIF(payload->>'code','')
      ),
      ''
    ) AS code,

    -- raw reason (best effort)
    COALESCE(
      NULLIF(payload->>'error',''),
      NULLIF(payload->>'exception',''),
      NULLIF(payload->>'exc',''),
      NULLIF(payload->>'exc_type',''),
      NULLIF(payload->>'detail',''),
      NULLIF(payload->>'message',''),
      NULLIF(message,''),
      COALESCE(event_type, legacy_type, 'unknown')
    ) AS reason_raw
  FROM err
  WHERE is_error = true
),
enriched AS (
  SELECT
    b.id,
    b.event_ts,
    b.source,
    COALESCE(b.event_type, b.legacy_type, 'unknown') AS kind,
    b.event_type,
    b.legacy_type,
    b.severity,
    b.ok,
    b.correlation_id,
    b.actor,
    b.message,
    b.payload,
    b.action,
    b.code,
    b.reason_raw,

    -- normalized reason signature
    LEFT(
      regexp_replace(
        regexp_replace(
          regexp_replace(
            regexp_replace(
              LOWER(TRIM(COALESCE(b.reason_raw,''))),
              E'[\\r\\n\\t]+', ' ', 'g'
            ),
            E'\\s+', ' ', 'g'
          ),
          '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{uuid}', 'gi'
        ),
        E'\\b\\d+\\b', '{n}', 'g'
      ),
      :reason_chars::int
    ) AS reason_sig,

    -- triage bucket (heuristic)
    CASE
      WHEN (
        b.reason_raw ILIKE '%does not exist%'
        OR b.reason_raw ILIKE '%undefined table%'
        OR b.reason_raw ILIKE '%undefined column%'
        OR b.reason_raw ILIKE '%schema % does not exist%'
        OR b.reason_raw ILIKE '%relation % does not exist%'
        OR b.reason_raw ILIKE '%column % does not exist%'
        OR b.reason_raw ILIKE '%syntax error%'
      ) THEN 'schema/ddl'

      WHEN (
        b.reason_raw ILIKE '%not null violation%'
        OR b.reason_raw ILIKE '%null value in column%'
        OR b.reason_raw ILIKE '%foreign key%'
        OR b.reason_raw ILIKE '%violates check constraint%'
        OR b.reason_raw ILIKE '%unique violation%'
        OR b.reason_raw ILIKE '%duplicate key%'
        OR b.reason_raw ILIKE '%invalid input syntax%'
      ) THEN 'data/integrity'

      WHEN (
        b.reason_raw ILIKE '%permission denied%'
        OR b.reason_raw ILIKE '%unauthorized%'
        OR b.reason_raw ILIKE '%forbidden%'
        OR b.reason_raw ILIKE '%not authorized%'
        OR b.reason_raw ILIKE '%invalid token%'
        OR b.reason_raw ILIKE '%jwt%'
      ) THEN 'authz/authn'

      WHEN (
        b.reason_raw ILIKE '%deadlock%'
        OR b.reason_raw ILIKE '%could not serialize%'
        OR b.reason_raw ILIKE '%lock timeout%'
        OR b.reason_raw ILIKE '%timeout%'
        OR b.reason_raw ILIKE '%connection refused%'
        OR b.reason_raw ILIKE '%connection reset%'
        OR b.reason_raw ILIKE '%broken pipe%'
        OR b.reason_raw ILIKE '%temporarily unavailable%'
      ) THEN 'transient/infra'

      WHEN (
        b.reason_raw ILIKE '%validation%'
        OR b.reason_raw ILIKE '%unprocessable entity%'
        OR b.reason_raw ILIKE '%bad request%'
        OR b.reason_raw ILIKE '%not found%'
        OR b.reason_raw ILIKE '% 404 %'
        OR b.reason_raw ILIKE '% 422 %'
        OR b.reason_raw ILIKE '% 400 %'
      ) THEN 'client/input'

      ELSE 'other'
    END AS triage_bucket,

    -- expected vs actionable (heuristic)
    CASE
      WHEN (
        b.reason_raw ILIKE '%deadlock%'
        OR b.reason_raw ILIKE '%could not serialize%'
        OR b.reason_raw ILIKE '%lock timeout%'
        OR b.reason_raw ILIKE '%timeout%'
        OR b.reason_raw ILIKE '%connection %'
        OR b.reason_raw ILIKE '%validation%'
        OR b.reason_raw ILIKE '%unprocessable entity%'
        OR b.reason_raw ILIKE '%bad request%'
        OR b.reason_raw ILIKE '%not found%'
      ) THEN 'expected'

      WHEN (
        b.reason_raw ILIKE '%does not exist%'
        OR b.reason_raw ILIKE '%syntax error%'
        OR b.reason_raw ILIKE '%not null violation%'
        OR b.reason_raw ILIKE '%foreign key%'
        OR b.reason_raw ILIKE '%permission denied%'
        OR b.reason_raw ILIKE '%unauthorized%'
        OR b.reason_raw ILIKE '%duplicate key%'
        OR b.reason_raw ILIKE '%unique violation%'
        OR b.reason_raw ILIKE '%invalid input syntax%'
      ) THEN 'actionable'

      ELSE 'actionable'
    END AS triage_class
  FROM base b
)
SELECT * FROM enriched;

ANALYZE temp_ops_event_err;

CREATE INDEX IF NOT EXISTS tmp_ops_err_kind_idx       ON temp_ops_event_err(kind);
CREATE INDEX IF NOT EXISTS tmp_ops_err_source_idx     ON temp_ops_event_err(source);
CREATE INDEX IF NOT EXISTS tmp_ops_err_ts_idx         ON temp_ops_event_err(event_ts DESC);

\echo ''
\echo '--- Summary ---'
SELECT
  COUNT(*) AS error_events_7d,
  COUNT(DISTINCT source) AS sources,
  COUNT(DISTINCT kind)   AS kinds,
  MIN(event_ts)          AS first_seen,
  MAX(event_ts)          AS last_seen
FROM temp_ops_event_err;

\echo ''
\echo '--- Errors by day ---'
SELECT
  date_trunc('day', event_ts) AS day,
  COUNT(*) AS cnt
FROM temp_ops_event_err
GROUP BY 1
ORDER BY 1 DESC;

\echo ''
\echo '--- Top groupings: source + kind + action (top :'top_groups') ---'
SELECT
  source,
  kind,
  COALESCE(action,'(none)') AS action,
  COUNT(*) AS cnt,
  COUNT(DISTINCT reason_sig) AS distinct_reasons,
  MAX(event_ts) AS last_seen
FROM temp_ops_event_err
GROUP BY 1,2,3
ORDER BY cnt DESC, last_seen DESC
LIMIT :top_groups;

\echo ''
\echo '--- Triage split (expected vs actionable) ---'
SELECT
  triage_class,
  triage_bucket,
  COUNT(*) AS cnt,
  MAX(event_ts) AS last_seen
FROM temp_ops_event_err
GROUP BY 1,2
ORDER BY cnt DESC;

\echo ''
\echo '--- Top reasons (normalized) (top :'top_reasons') ---'
WITH agg AS (
  SELECT
    source,
    kind,
    triage_class,
    triage_bucket,
    reason_sig,
    COUNT(*) AS cnt,
    MAX(event_ts) AS last_seen
  FROM temp_ops_event_err
  GROUP BY 1,2,3,4,5
)
SELECT *
FROM agg
ORDER BY cnt DESC, last_seen DESC
LIMIT :top_reasons;

\echo ''
\echo '--- 5 payload samples for each top reason ---'
WITH agg AS (
  SELECT
    source,
    kind,
    triage_class,
    triage_bucket,
    reason_sig,
    COUNT(*) AS cnt,
    MAX(event_ts) AS last_seen
  FROM temp_ops_event_err
  GROUP BY 1,2,3,4,5
),
top AS (
  SELECT *
  FROM agg
  ORDER BY cnt DESC, last_seen DESC
  LIMIT :top_reasons
),
samples AS (
  SELECT
    t.source,
    t.kind,
    t.triage_class,
    t.triage_bucket,
    t.reason_sig,
    t.cnt,
    e.id,
    e.event_ts,
    COALESCE(e.action,'(none)') AS action,
    LEFT(COALESCE(e.message,''), :msg_chars::int) AS message_excerpt,
    LEFT(jsonb_pretty(e.payload)::text, :payload_chars::int) AS payload_excerpt,
    ROW_NUMBER() OVER (PARTITION BY t.source, t.kind, t.reason_sig ORDER BY e.event_ts DESC) AS rn
  FROM top t
  JOIN temp_ops_event_err e
    ON e.source = t.source
   AND e.kind   = t.kind
   AND e.reason_sig = t.reason_sig
)
SELECT
  source, kind, triage_class, triage_bucket, cnt,
  id, event_ts, action, message_excerpt, payload_excerpt, rn
FROM samples
WHERE rn <= :samples_per_reason
ORDER BY cnt DESC, source, kind, reason_sig, rn;

\echo '================================================================='
\echo 'END'

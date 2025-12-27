CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.autoplan_daily_v AS
SELECT
    date(ts) AS d,
    COALESCE(plan_name, thresholds->>'flow_plan', 'unknown') AS flow_plan,

    count(*) AS total_events,

    count(*) FILTER (WHERE decision = 'apply')   AS apply_decisions,
    count(*) FILTER (WHERE decision = 'confirm') AS confirm_decisions,
    count(*) FILTER (WHERE decision = 'noop')    AS noop_decisions,

    count(*) FILTER (WHERE applied IS TRUE)  AS applied_events,
    count(*) FILTER (WHERE applied IS FALSE) AS not_applied_events,

    count(DISTINCT trip_id) FILTER (WHERE trip_id IS NOT NULL) AS trips_touched
FROM public.autoplan_audit
GROUP BY d, COALESCE(plan_name, thresholds->>'flow_plan', 'unknown');

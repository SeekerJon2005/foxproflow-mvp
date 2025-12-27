-- file: scripts/sql/verify/20251222_hotfix_eventlog_corrid_trucks_crm_smoke.sql
-- FoxProFlow • Verify/Smoke • Hotfix: correlation_id + missing objects

\set ON_ERROR_STOP on
\pset pager off

SELECT
  to_regclass('ops.event_log')                 AS ops_event_log,
  to_regclass('public.trucks')                 AS public_trucks,
  to_regclass('crm.leads_trial_candidates_v')  AS crm_leads_trial_candidates_v;

-- correlation_id present?
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='ops' AND table_name='event_log' AND column_name='correlation_id';

-- trucks exists and queryable
SELECT count(*) AS trucks_cnt FROM public.trucks;

-- view exists and queryable (must be 0)
SELECT count(*) AS trial_candidates_cnt FROM crm.leads_trial_candidates_v;

-- quick show view columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='crm' AND table_name='leads_trial_candidates_v'
ORDER BY ordinal_position;

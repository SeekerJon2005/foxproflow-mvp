-- 20251223_crm_salesfox_core_smoke.sql
-- Verify/Smoke: CRM SalesFox core DB contract (B-dev)

\set ON_ERROR_STOP on
\pset pager off

select now() as ts_now, current_database() as db, current_user as db_user;

DO $$
DECLARE
  missing text[] := '{}';
BEGIN
  -- relations
  IF to_regclass('crm.leads') IS NULL THEN missing := array_append(missing,'crm.leads'); END IF;
  IF to_regclass('crm.sales_sessions') IS NULL THEN missing := array_append(missing,'crm.sales_sessions'); END IF;
  IF to_regclass('crm.accounts') IS NULL THEN missing := array_append(missing,'crm.accounts'); END IF;
  IF to_regclass('crm.subscriptions_v1') IS NULL THEN missing := array_append(missing,'crm.subscriptions_v1'); END IF;
  IF to_regclass('crm.subscriptions_v2') IS NULL THEN missing := array_append(missing,'crm.subscriptions_v2'); END IF;
  IF to_regclass('crm.onboarding_sessions') IS NULL THEN missing := array_append(missing,'crm.onboarding_sessions'); END IF;

  IF to_regclass('crm.account_overview_v') IS NULL THEN missing := array_append(missing,'crm.account_overview_v'); END IF;
  IF to_regclass('crm.trial_accounts_overview_v') IS NULL THEN missing := array_append(missing,'crm.trial_accounts_overview_v'); END IF;

  IF to_regprocedure('crm.fn_lead_win_trial_and_onboarding(bigint,text,text,text,numeric,text,integer)') IS NULL THEN
    missing := array_append(missing,'crm.fn_lead_win_trial_and_onboarding(bigint,text,text,text,numeric,text,integer)');
  END IF;

  IF array_length(missing,1) IS NOT NULL THEN
    RAISE EXCEPTION 'CRM SalesFox core FAILED: missing => %', array_to_string(missing, ', ');
  END IF;
END $$;

-- leads required columns
select column_name, data_type
from information_schema.columns
where table_schema='crm' and table_name='leads'
  and column_name in ('id','source','status','company_name','contact_name','email','phone','country','region','payload','last_session_id','created_at','updated_at')
order by 1;

-- sales_sessions required columns
select column_name, data_type
from information_schema.columns
where table_schema='crm' and table_name='sales_sessions'
  and column_name in ('id','lead_id','channel','status','transcript','summary','last_event_id','created_at','updated_at')
order by 1;

-- account_overview_v required columns (used by tasks_salesfox.py)
select column_name, data_type
from information_schema.columns
where table_schema='crm' and table_name='account_overview_v'
  and column_name in ('account_id','trial_until_v2','trial_ends_at_v1')
order by 1;

-- trial_accounts_overview_v required columns (used by routers/crm.py)
select column_name, data_type
from information_schema.columns
where table_schema='crm' and table_name='trial_accounts_overview_v'
  and column_name in ('account_id','company_name','product_code','plan_code','trial_until','is_expired','trial_status','days_left')
order by 1;

-- quick no-side-effect call (expects 0 rows for non-existent lead)
select *
from crm.fn_lead_win_trial_and_onboarding(-1,'logistics','mvp-5-15-trucks','RUB',0,'monthly',30);

select 'OK: CRM SalesFox core suite passed' as status;

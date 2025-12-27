-- 20251223_cp1_db_core_suite.sql
-- Purpose: CP1 "CRM-MVP ready to pilot without fires" — DB invariants fail-fast.
-- Owner: C-sql
-- Run example:
--   psql -v ON_ERROR_STOP=1 -f scripts/sql/verify/20251223_cp1_db_core_suite.sql

\pset pager off

select now() as ts_now, current_database() as db, current_user as db_user;

-- 1) Required relations (existence)
do $$
declare
  missing text[] := '{}';
begin
  if to_regclass('sec.roles')                  is null then missing := array_append(missing,'sec.roles'); end if;
  if to_regclass('sec.subject_roles')          is null then missing := array_append(missing,'sec.subject_roles'); end if;
  if to_regclass('sec.policies')               is null then missing := array_append(missing,'sec.policies'); end if;
  if to_regclass('sec.role_policy_bindings')   is null then missing := array_append(missing,'sec.role_policy_bindings'); end if;

  if to_regclass('dev.dev_task')               is null then missing := array_append(missing,'dev.dev_task'); end if;

  if to_regclass('ops.event_log')              is null then missing := array_append(missing,'ops.event_log'); end if;

  if to_regclass('planner.kpi_snapshots')      is null then missing := array_append(missing,'planner.kpi_snapshots'); end if;
  if to_regclass('planner.planner_kpi_daily')  is null then missing := array_append(missing,'planner.planner_kpi_daily'); end if;

  if to_regclass('public.trips')               is null then missing := array_append(missing,'public.trips'); end if;
  if to_regclass('public.trip_segments')       is null then missing := array_append(missing,'public.trip_segments'); end if;

  if to_regclass('public.trucks')              is null then missing := array_append(missing,'public.trucks'); end if;

  if to_regclass('crm.leads_trial_candidates_v') is null then missing := array_append(missing,'crm.leads_trial_candidates_v'); end if;

  if array_length(missing, 1) is not null then
    raise exception 'CP1 DB core suite FAILED: missing relations => %', array_to_string(missing, ', ');
  end if;
end $$;

-- 2) Required columns (contract-ish checks)
do $$
begin
  if not exists (
    select 1
    from information_schema.columns
    where table_schema='ops' and table_name='event_log' and column_name='correlation_id'
  ) then
    raise exception 'CP1 DB core suite FAILED: missing column ops.event_log.correlation_id';
  end if;

  if not exists (
    select 1 from information_schema.columns
    where table_schema='public' and table_name='trips' and column_name='created_at'
  ) then
    raise exception 'CP1 DB core suite FAILED: missing column public.trips.created_at';
  end if;

  if not exists (
    select 1 from information_schema.columns
    where table_schema='public' and table_name='trips' and column_name='confirmed_at'
  ) then
    raise exception 'CP1 DB core suite FAILED: missing column public.trips.confirmed_at';
  end if;

  -- trip_segments minimal routing compat columns
  if not exists (select 1 from information_schema.columns where table_schema='public' and table_name='trip_segments' and column_name='trip_id') then
    raise exception 'CP1 DB core suite FAILED: missing column public.trip_segments.trip_id';
  end if;
  if not exists (select 1 from information_schema.columns where table_schema='public' and table_name='trip_segments' and column_name='segment_order') then
    raise exception 'CP1 DB core suite FAILED: missing column public.trip_segments.segment_order';
  end if;
  if not exists (select 1 from information_schema.columns where table_schema='public' and table_name='trip_segments' and column_name='origin_region') then
    raise exception 'CP1 DB core suite FAILED: missing column public.trip_segments.origin_region';
  end if;
  if not exists (select 1 from information_schema.columns where table_schema='public' and table_name='trip_segments' and column_name='dest_region') then
    raise exception 'CP1 DB core suite FAILED: missing column public.trip_segments.dest_region';
  end if;
end $$;

-- 3) Quick evidence (lightweight)
select
  (select count(*) from sec.roles)                as sec_roles_cnt,
  (select count(*) from sec.policies)             as sec_policies_cnt,
  (select count(*) from sec.role_policy_bindings) as sec_rpb_cnt;

select
  (select count(*) from dev.dev_task) as dev_task_cnt;

select
  (select max(ts) from planner.kpi_snapshots) as kpi_last_ts;

-- Show relkind for planner_kpi_daily (expect 'm' = matview; 'r' = table is also acceptable operationally)
select n.nspname as schema_name, c.relname as rel_name, c.relkind
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname='planner' and c.relname='planner_kpi_daily';

select 'OK: CP1 DB core suite passed' as status;
